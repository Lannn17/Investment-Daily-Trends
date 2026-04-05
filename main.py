#!/usr/bin/env python3
"""Investment Daily Trends — automated daily investment digest."""

import os
import datetime

from src.config import (
    TEST_MODE, FULLTEST_MODE, UITEST_MODE, FORCE_EMAIL,
    BASE, JST, get_run_type,
    INDICES_TICKERS, INDICES_LABELS,
    COMMODITIES_TICKERS, COMMODITIES_LABELS,
    FX_TICKERS, FX_LABELS,
    WATCHLIST_TICKERS, WATCHLIST_NAMES,
    MARKET_NEWS_URLS, JAPAN_NEWS_URLS,
    MARKET_NEWS_MAX, JAPAN_NEWS_MAX, HOT_MARKET_NEWS_MAX,
    GEMINI_API_KEY, WATCHLIST_MODEL_CHAIN,
)
from src.state import (
    load_last_run, save_last_run,
    load_morning_bench, save_morning_bench,
    save_render_cache, load_render_cache,
    text_fingerprint,
)
from src.price import fetch_price_list, fetch_price_item, _placeholder
from src.hot_sectors import detect_hot_sectors, fetch_ticker_news
from src.ai_client import analyze_watchlist
from src.news import process_news_section
from src.output import build_render_context, render_daily_html, render_email_html, send_daily_email

# ── Bootstrap ─────────────────────────────────────────────────────────────────
os.makedirs(BASE, exist_ok=True)

run_type     = get_run_type()
now          = datetime.datetime.now(JST)
WEEKEND_MODE = now.weekday() >= 5  # Saturday=5, Sunday=6

# ── Edition label ─────────────────────────────────────────────────────────────
if WEEKEND_MODE:
    _brief = 'Daily Markets · Weekend'
elif run_type == 'morning':
    _brief = 'Daily Markets · Morning'
else:
    _brief = 'Daily Markets · Evening'

if UITEST_MODE:
    edition = f'[UITEST] {_brief}'
elif FULLTEST_MODE:
    edition = f'[FULLTEST] {_brief}'
elif TEST_MODE:
    edition = f'[TEST] {_brief}'
else:
    edition = _brief

# ── UI Test: load cache, skip all network/AI calls ────────────────────────────
if UITEST_MODE:
    print(f"[uitest] time={now.strftime('%Y-%m-%d %H:%M:%S')} JST - loading render cache, no API calls")
    _c = load_render_cache()
    indices_data        = _c['indices']
    commodities_data    = _c['commodities']
    fx_data             = _c['fx']
    hist_dates          = _c.get('hist_dates', [])
    hot_markets         = _c['hot_markets']
    watchlist_items     = _c['watchlist']
    market_news_entries = _c['market_news']
    japan_news_entries  = _c['japan_news']

else:
    print(f"[run] type={run_type}  time={now.strftime('%Y-%m-%d %H:%M:%S')} JST")

    last_run_links, last_run_fps = load_last_run()
    morning_bench      = load_morning_bench() if run_type == 'evening' else {}
    seen_links         = set()
    current_run_fps    = []
    current_run_links  = set()
    morning_bench_data = {}

    # ── Step 1: Price data ────────────────────────────────────────────────────
    print("[prices] Fetching indices...")
    indices_data = fetch_price_list(INDICES_TICKERS, INDICES_LABELS)

    print("[prices] Fetching commodities...")
    commodities_data = fetch_price_list(COMMODITIES_TICKERS, COMMODITIES_LABELS)

    print("[prices] Fetching FX...")
    fx_data = fetch_price_list(FX_TICKERS, FX_LABELS)

    hist_dates = next(
        (item['history_dates'] for item in indices_data + commodities_data if item.get('history_dates')),
        []
    )

    # ── Step 2: Hot sector detection (two-stage) ──────────────────────────────
    if WEEKEND_MODE:
        print("[hot_sectors] Skipped — weekend, markets closed")
        hot_markets = []
    else:
        print("[hot_sectors] Detecting hot sectors...")
        hot_markets = detect_hot_sectors()
    if TEST_MODE:
        hot_markets = hot_markets[:2]

    for hm in hot_markets:
        hm['news'] = fetch_ticker_news(hm['etf'], max_items=HOT_MARKET_NEWS_MAX)
        print(f"  [hot_sectors] {hm['label']}: fetched {len(hm['news'])} news items")

    # ── Step 3: Combined AI analysis for all Block-1 + Watchlist items ────────
    def _init_ai_fields(items):
        for item in items:
            item.setdefault('name',        item.get('label', item['ticker']))
            item.setdefault('news_titles', [n.title for n in fetch_ticker_news(item['ticker'], max_items=3)])
            item['analysis']    = None
            item['outlook']     = 'neutral'
            item['outlook_css'] = 'neutral'

    print("[ai] Fetching news for indices / commodities / FX / hot markets...")
    _init_ai_fields(indices_data)
    _init_ai_fields(commodities_data)
    _init_ai_fields(fx_data)

    for hm in hot_markets:
        mover_ctx = [f"{m['ticker']} {m['change_pct_fmt']}" for m in hm.get('top_movers', [])]
        hm.update({
            'ticker':      hm['etf'],
            'name':        hm['label'],
            'news_titles': [n.title for n in hm['news']] + mover_ctx,
            'analysis':    None,
            'outlook':     'neutral',
            'outlook_css': 'neutral',
        })

    print("[watchlist] Fetching prices...")
    watchlist_items = []
    for ticker in WATCHLIST_TICKERS:
        label = WATCHLIST_NAMES.get(ticker, ticker)
        item  = fetch_price_item(ticker, label)
        if item is None:
            item = _placeholder(ticker, label)
        item['name']        = WATCHLIST_NAMES.get(ticker, ticker)
        item['news_titles'] = [n.title for n in fetch_ticker_news(ticker, max_items=3)]
        item['analysis']    = None
        item['outlook']     = 'neutral'
        item['outlook_css'] = 'neutral'
        watchlist_items.append(item)

    if GEMINI_API_KEY and WATCHLIST_MODEL_CHAIN:
        all_ai_items = (
            [i for i in indices_data      if i['price_fmt'] != 'N/A'] +
            [i for i in commodities_data  if i['price_fmt'] != 'N/A'] +
            [i for i in fx_data           if i['price_fmt'] != 'N/A'] +
            [hm for hm in hot_markets     if hm.get('price_fmt', 'N/A') != 'N/A'] +
            watchlist_items
        )
        if all_ai_items:
            print(f"[ai] Combined analysis for {len(all_ai_items)} items (1 API call)...")
            analyses = analyze_watchlist(all_ai_items, run_type=run_type)

            def _apply_analysis(items):
                for item in items:
                    a = analyses.get(item['ticker'])
                    if a:
                        item['outlook'] = a.get('outlook', 'neutral').lower()
                        if item['outlook'] not in ('bullish', 'bearish', 'neutral'):
                            item['outlook'] = 'neutral'
                        item['outlook_css'] = item['outlook']
                        today_text  = a.get('today', '')
                        reason_text = a.get('outlook_reason', '')
                        item['analysis'] = today_text + (f'\n{reason_text}' if reason_text else '')

            _apply_analysis(indices_data)
            _apply_analysis(commodities_data)
            _apply_analysis(fx_data)
            _apply_analysis(hot_markets)
            _apply_analysis(watchlist_items)

    # ── Step 4: News sections ─────────────────────────────────────────────────
    if WEEKEND_MODE:
        market_news_topic = '全球财经市场 · 周末要闻速览'
        japan_news_topic  = '日本金融市场 · 周末动态'
    elif run_type == 'morning':
        market_news_topic = '全球财经市场 · 美欧隔夜复盘及亚市开盘前瞻'
        japan_news_topic  = '日本金融市场 · 今日开盘前瞻'
    else:
        market_news_topic = '全球财经市场 · 欧市盘中动态及美股开盘前瞻'
        japan_news_topic  = '日本金融市场 · 今日收盘复盘'

    print("[news] Processing market_news...")
    market_news_entries, mn_bench = process_news_section(
        MARKET_NEWS_URLS, MARKET_NEWS_MAX, 'market_news', market_news_topic,
        last_run_links, last_run_fps, current_run_fps, seen_links,
        run_type=run_type, morning_bench=morning_bench,
    )
    for e in market_news_entries:
        current_run_links.add(e.link)
    if run_type == 'morning' and mn_bench:
        morning_bench_data['market_news'] = mn_bench

    print("[news] Processing japan_news...")
    japan_news_entries, jn_bench = process_news_section(
        JAPAN_NEWS_URLS, JAPAN_NEWS_MAX, 'japan_news', japan_news_topic,
        last_run_links, last_run_fps, current_run_fps, seen_links,
        run_type=run_type, morning_bench=morning_bench,
    )
    for e in japan_news_entries:
        current_run_links.add(e.link)
    if run_type == 'morning' and jn_bench:
        morning_bench_data['japan_news'] = jn_bench

    # ── Step 5: Save state ────────────────────────────────────────────────────
    if FULLTEST_MODE:
        for path in [os.path.join(BASE, 'last_run.json'), os.path.join(BASE, 'morning_bench.json')]:
            try:
                os.remove(path)
            except Exception:
                pass
        print("[FULLTEST] State cleared — next run starts fresh")
    elif TEST_MODE:
        print("[TEST] State not saved - next run re-fetches same articles")
    else:
        all_fps = [text_fingerprint(e.title, getattr(e, 'article', e.title))
                   for e in market_news_entries + japan_news_entries]
        save_last_run(current_run_links, all_fps)
        if run_type == 'morning':
            save_morning_bench(morning_bench_data)

    if not FULLTEST_MODE:
        save_render_cache(dict(
            indices=indices_data, commodities=commodities_data, fx=fx_data,
            hist_dates=hist_dates, watchlist=watchlist_items,
            market_news=market_news_entries, japan_news=japan_news_entries,
            hot_markets=hot_markets,
        ))

# ── Step 6: Render ────────────────────────────────────────────────────────────
ctx = build_render_context(
    run_type, WEEKEND_MODE, now, edition,
    indices_data, commodities_data, fx_data,
    hist_dates, watchlist_items,
    market_news_entries, japan_news_entries, hot_markets,
)
render_daily_html(ctx)
email_html = render_email_html(ctx)

# ── Step 7: Send email ────────────────────────────────────────────────────────
if FORCE_EMAIL or not (TEST_MODE or FULLTEST_MODE or UITEST_MODE):
    send_daily_email(email_html, edition, now)
else:
    print("[email] Skipped in test mode - use --email to force send")

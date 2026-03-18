#!/usr/bin/env python3
"""Investment Daily Trends — automated daily investment digest."""

import os
import json
import re
import math
import time
import datetime
import calendar
import smtplib
import argparse
import configparser
from difflib import SequenceMatcher
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from types import SimpleNamespace

import feedparser
import requests
import yfinance as yf
from google import genai
from google.genai import types as genai_types
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from jinja2 import Template
from dotenv import load_dotenv
import pandas as pd

load_dotenv('.env')

# ── CLI args ──────────────────────────────────────────────────────────────────
_ap = argparse.ArgumentParser()
_ap.add_argument('--test',     action='store_true', help='Quick test: 2 articles/section, state not saved')
_ap.add_argument('--fulltest', action='store_true', help='Full test: production count, state cleared after')
_ap.add_argument('--uitest',   action='store_true', help='UI test: skip all API/data calls, render from cache only')
_ap.add_argument('--email',    action='store_true', help='Force send email even in test/uitest mode')
_ap.add_argument('--edition',  choices=['morning', 'evening'], default=None)
_args = _ap.parse_args()
TEST_MODE     = _args.test
FULLTEST_MODE = _args.fulltest
UITEST_MODE   = _args.uitest
FORCE_EMAIL   = _args.email

# ── Config ────────────────────────────────────────────────────────────────────
config = configparser.ConfigParser()
config.read('config.ini')

def get_cfg(sec, key, default=None):
    val = config.get(sec, key, fallback=default)
    return val.strip('"') if val else default

BASE                   = get_cfg('cfg', 'base', 'docs/')
SIMILARITY_THRESHOLD   = float(get_cfg('cfg', 'similarity_threshold',   '0.70'))
INTRA_BATCH_THRESHOLD  = float(get_cfg('cfg', 'intra_batch_threshold',  '0.60'))
KEYWORD_LENGTH         = int(get_cfg('cfg', 'keyword_length', '3'))
SUMMARY_LENGTH         = int(get_cfg('cfg', 'summary_length', '150'))
HOT_MARKET_THRESHOLD   = float(get_cfg('cfg', 'hot_market_threshold', '0.02'))
MARKET_NEWS_MAX        = int(get_cfg('cfg', 'market_news_max_items', '5'))
JAPAN_NEWS_MAX         = int(get_cfg('cfg', 'japan_news_max_items',  '3'))
HOT_MARKET_NEWS_MAX    = int(get_cfg('cfg', 'hot_market_news_max_items', '2'))

INDICES_TICKERS    = [t.strip() for t in get_cfg('indices',    'tickers', '').split(',') if t.strip()]
INDICES_LABELS     = [l.strip() for l in get_cfg('indices',    'labels',  '').split(',') if l.strip()]
COMMODITIES_TICKERS = [t.strip() for t in get_cfg('commodities', 'tickers', '').split(',') if t.strip()]
COMMODITIES_LABELS  = [l.strip() for l in get_cfg('commodities', 'labels',  '').split(',') if l.strip()]
FX_TICKERS         = [t.strip() for t in get_cfg('fx', 'tickers', '').split(',') if t.strip()]
FX_LABELS          = [l.strip() for l in get_cfg('fx', 'labels',  '').split(',') if l.strip()]

HOT_MARKET_ETFS    = [t.strip() for t in get_cfg('hot_markets', 'etfs',   '').split(',') if t.strip()]
HOT_MARKET_LABELS  = [l.strip() for l in get_cfg('hot_markets', 'labels', '').split(',') if l.strip()]

MARKET_NEWS_URLS   = [u.strip() for u in get_cfg('market_news', 'url', '').split(',') if u.strip()]
JAPAN_NEWS_URLS    = [u.strip() for u in get_cfg('japan_news',  'url', '').split(',') if u.strip()]

# ── Gemini setup ──────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DEFAULT_MODEL  = os.environ.get('GEMINI_MODEL') or 'gemini-3.1-flash-lite-preview'

def _chain(*models):
    return [m.strip() for m in models if m and m.strip()]

SCORE_MODEL_CHAIN     = _chain(os.environ.get('SCORE_MODEL'),     DEFAULT_MODEL)
TRANSLATE_MODEL_CHAIN = _chain(os.environ.get('TRANSLATE_MODEL'), DEFAULT_MODEL)
SUMMARY_MODEL_CHAIN   = _chain(os.environ.get('SUMMARY_MODEL'),   DEFAULT_MODEL)
WATCHLIST_MODEL_CHAIN = _chain(os.environ.get('WATCHLIST_MODEL'), DEFAULT_MODEL)

_gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

print(f"[models] score={SCORE_MODEL_CHAIN} translate={TRANSLATE_MODEL_CHAIN} "
      f"summary={SUMMARY_MODEL_CHAIN} watchlist={WATCHLIST_MODEL_CHAIN}")

# ── Watchlist ─────────────────────────────────────────────────────────────────
# Built-in display names; watchlist.json names field takes priority
BUILTIN_NAMES = {
    'IAU':    'iShares Gold Trust',
    'NEM':    'Newmont Corporation',
    'NVDA':   'NVIDIA',
    'TSM':    'Taiwan Semiconductor',
    'BRK-B':  'Berkshire Hathaway B',
    'LMT':    'Lockheed Martin',
    '7203.T': 'Toyota Motor',
    '9984.T': 'SoftBank Group',
    'INDA':   'iShares MSCI India ETF',
}

def load_watchlist():
    try:
        with open('watchlist.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        tickers = data.get('tickers', [])
        names   = {**BUILTIN_NAMES, **data.get('names', {})}
        return tickers, names
    except Exception as e:
        print(f"Warning: could not load watchlist.json: {e}")
        return [], BUILTIN_NAMES

WATCHLIST_TICKERS, WATCHLIST_NAMES = load_watchlist()

# ── Sector universe ───────────────────────────────────────────────────────────
def load_sector_universe():
    try:
        with open('sector_universe.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not load sector_universe.json: {e}")
        return {'sectors': []}

SECTOR_UNIVERSE = load_sector_universe()

# ── Timezone & run type ───────────────────────────────────────────────────────
JST = datetime.timezone(datetime.timedelta(hours=9))

def get_run_type():
    if _args.edition:
        return _args.edition
    hour = datetime.datetime.now(JST).hour
    return 'morning' if hour < 14 else 'evening'

# ── State persistence (news dedup) ────────────────────────────────────────────
def load_last_run():
    try:
        with open(os.path.join(BASE, 'last_run.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get('links', [])), data.get('fingerprints', [])
    except Exception:
        return set(), []

def save_last_run(links, fingerprints):
    try:
        with open(os.path.join(BASE, 'last_run.json'), 'w', encoding='utf-8') as f:
            json.dump({'links': list(links), 'fingerprints': fingerprints},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: could not save last_run: {e}")

def load_morning_bench():
    try:
        with open(os.path.join(BASE, 'morning_bench.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_morning_bench(bench):
    try:
        with open(os.path.join(BASE, 'morning_bench.json'), 'w', encoding='utf-8') as f:
            json.dump(bench, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: could not save morning_bench: {e}")

def _entry_to_dict(e):
    """Convert SimpleNamespace news entry to plain dict for JSON serialisation."""
    return e.__dict__ if hasattr(e, '__dict__') else dict(e)

def save_render_cache(ctx):
    """Save render context to JSON so --uitest can skip all API calls."""
    try:
        cache = {}
        for key, val in ctx.items():
            if key in ('market_news', 'japan_news'):
                cache[key] = [_entry_to_dict(e) for e in val]
            elif key == 'hot_markets':
                cache[key] = [
                    {**{k: v for k, v in hm.items() if k != 'news'},
                     'news': [_entry_to_dict(n) for n in hm.get('news', [])]}
                    for hm in val
                ]
            else:
                cache[key] = val
        with open(os.path.join(BASE, 'render_cache.json'), 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: could not save render_cache: {e}")

def load_render_cache():
    """Load render context from JSON cache for --uitest mode."""
    with open(os.path.join(BASE, 'render_cache.json'), 'r', encoding='utf-8') as f:
        cache = json.load(f)
    for key in ('market_news', 'japan_news'):
        cache[key] = [SimpleNamespace(**d) for d in cache.get(key, [])]
    for hm in cache.get('hot_markets', []):
        hm['news'] = [SimpleNamespace(**n) for n in hm.get('news', [])]
    return cache

# ── Dedup helpers ─────────────────────────────────────────────────────────────
def text_fingerprint(title, text):
    return (title + ' ' + text[:400]).lower().strip()

def is_duplicate(fp, seen_fps, threshold=None):
    thr = threshold if threshold is not None else SIMILARITY_THRESHOLD
    return any(SequenceMatcher(None, fp, s).ratio() >= thr for s in seen_fps)

# ── Price formatting ──────────────────────────────────────────────────────────
def ticker_url(ticker):
    return f'https://finance.yahoo.com/quote/{ticker}'

def format_price(price):
    """Smart price formatter based on magnitude."""
    if price is None or (isinstance(price, float) and math.isnan(price)):
        return 'N/A'
    if price >= 10000:
        return f'{price:,.0f}'
    elif price >= 1000:
        return f'{price:,.2f}'
    elif price >= 100:
        return f'{price:.2f}'
    elif price >= 10:
        return f'{price:.3f}'
    else:
        return f'{price:.4f}'

def price_css(change):
    if change > 0:  return 'up'
    if change < 0:  return 'down'
    return 'flat'

def price_arrow(change):
    return '▲' if change >= 0 else '▼'

# ── Market close times (local hour) by UTC offset ────────────────────────────
# Bar timestamps from yfinance are midnight of the trading day in the local exchange tz.
# Adding the standard close hour gives the actual close time for that exchange.
_CLOSE_HOURS_BY_UTC_OFFSET = {
    -5.0: 16.0,   # EST  → NYSE/NASDAQ 16:00 EST  = 06:00 JST
    -4.0: 16.0,   # EDT  → NYSE/NASDAQ 16:00 EDT  = 05:00 JST
     9.0: 15.5,   # JST  → TSE         15:30 JST  = 15:30 JST
     8.0: 16.0,   # HKT/SGT            16:00       = 17:00 JST
     0.0: 16.5,   # GMT  → London      16:30 GMT  = 01:30 JST (+1d)
     1.0: 17.5,   # CET  → Frankfurt   17:30 CET  = 01:30 JST (+1d)
}

# ── yfinance price fetch ──────────────────────────────────────────────────────
def fetch_price_item(ticker, label):
    """Fetch today + 5-day history for one ticker. Returns dict or None."""
    try:
        hist = yf.Ticker(ticker).history(period='8d', auto_adjust=True)
        hist = hist[hist['Close'].notna()]
        if len(hist) < 2:
            print(f"  [price] Insufficient history for {ticker}")
            return None

        today = float(hist['Close'].iloc[-1])
        prev  = float(hist['Close'].iloc[-2])
        change     = today - prev
        change_pct = change / prev if prev else 0.0

        hist5       = hist['Close'].tail(5)
        start5      = float(hist5.iloc[0])
        end5        = float(hist5.iloc[-1])
        change_5d   = (end5 - start5) / start5 if start5 else 0.0

        # as_of: estimate the exchange close time in JST from bar timestamp + known close offset
        try:
            ts = hist.index[-1]
            if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                tz_offset_h = ts.tzinfo.utcoffset(ts).total_seconds() / 3600
                close_h = _CLOSE_HOURS_BY_UTC_OFFSET.get(tz_offset_h)
                if close_h is not None:
                    close_ts = ts + datetime.timedelta(hours=close_h)
                    as_of = close_ts.astimezone(JST).strftime('%m/%d %H:%M')
                else:
                    as_of = ts.astimezone(JST).strftime('%m/%d')  # unknown exchange: date only
            else:
                as_of = ts.replace(tzinfo=datetime.timezone.utc).astimezone(JST).strftime('%m/%d')
        except Exception:
            as_of = ''

        return {
            'ticker':          ticker,
            'label':           label,
            'url':             ticker_url(ticker),
            'price':           today,
            'price_fmt':       format_price(today),
            'change':          change,
            'change_fmt':      format_price(abs(change)),
            'change_pct':      change_pct,
            'change_pct_fmt':  f'{change_pct * 100:+.2f}%',
            'change_arrow':    price_arrow(change),
            'css':             price_css(change),
            'history':         [format_price(float(v)) for v in hist5.values],
            'history_dates':   [d.strftime('%m/%d') for d in hist5.index],
            'change_5d':       change_5d,
            'change_5d_fmt':   f'{change_5d * 100:+.2f}%',
            'css5d':           price_css(change_5d),
            'as_of':           as_of,
        }
    except Exception as e:
        print(f"  [price] Failed for {ticker}: {e}")
        return None

def _placeholder(ticker, label):
    return {
        'ticker': ticker, 'label': label, 'url': ticker_url(ticker),
        'price': None, 'price_fmt': 'N/A',
        'change': 0, 'change_fmt': 'N/A',
        'change_pct': 0, 'change_pct_fmt': 'N/A',
        'change_arrow': '-', 'css': 'flat',
        'history': [], 'history_dates': [],
        'change_5d': 0, 'change_5d_fmt': 'N/A', 'css5d': 'flat',
        'as_of': '',
    }

def fetch_price_list(tickers, labels):
    items = []
    for ticker, label in zip(tickers, labels):
        item = fetch_price_item(ticker, label)
        items.append(item if item else _placeholder(ticker, label))
    return items

# ── Hot market detection ──────────────────────────────────────────────────────
def batch_price_data(tickers):
    """Batch download daily price and % change for a list of tickers.
    Returns dict: ticker -> {price, price_fmt, pct, change_pct_fmt, change_arrow, css, url}
    """
    if not tickers:
        return {}
    try:
        raw = yf.download(list(tickers), period='2d', auto_adjust=True,
                          progress=False, threads=False)
        if raw.empty:
            return {}
        if isinstance(raw.columns, pd.MultiIndex):
            closes = raw['Close']
        else:
            t = tickers[0] if len(tickers) == 1 else None
            if t:
                closes = pd.DataFrame({t: raw['Close']})
            else:
                return {}
        result = {}
        for ticker in tickers:
            if ticker not in closes.columns:
                continue
            col = closes[ticker].dropna()
            if len(col) < 2:
                continue
            today = float(col.iloc[-1])
            prev  = float(col.iloc[-2])
            pct   = (today - prev) / prev if prev else 0.0
            result[ticker] = {
                'price':          today,
                'price_fmt':      format_price(today),
                'pct':            pct,
                'change_pct_fmt': f'{pct * 100:+.2f}%',
                'change_arrow':   price_arrow(pct),
                'css':            price_css(pct),
                'url':            ticker_url(ticker),
            }
        return result
    except Exception as e:
        print(f"  [batch_price_data] Failed: {e}")
        return {}


def detect_hot_sectors():
    """Two-stage hot sector detection using sector_universe.json.
    Stage 1: one batch download of all sector ETFs -> top movers above threshold.
    Stage 2: for each triggered sector, batch download constituents -> top 3 stocks.
    """
    sectors = SECTOR_UNIVERSE.get('sectors', [])
    if not sectors:
        return []

    # Stage 1: one call for all sector ETFs
    all_etfs = [s['etf'] for s in sectors]
    print(f"  [hot_sectors] Stage 1: screening {len(all_etfs)} sector ETFs...")
    etf_data = batch_price_data(all_etfs)

    sorted_etfs = sorted(etf_data.items(), key=lambda x: abs(x[1]['pct']), reverse=True)
    triggered = [(etf, d) for etf, d in sorted_etfs
                 if abs(d['pct']) >= HOT_MARKET_THRESHOLD][:5]

    if not triggered:
        print("  [hot_sectors] No sectors above threshold")
        return []

    sector_map = {s['etf']: s for s in sectors}
    hot = []

    for etf, price_data in triggered:
        info  = sector_map.get(etf, {})
        label = info.get('label', etf)
        print(f"  [hot_sectors] Triggered: {label} ({etf}) {price_data['change_pct_fmt']}")

        hm = {
            'country':             label,
            'label':               label,
            'etf':                 etf,
            'etf_source':          info.get('source', ''),
            'pct':                 price_data['pct'],
            'url':                 ticker_url(etf),
            'price_fmt':           price_data['price_fmt'],
            'change_pct_fmt':      price_data['change_pct_fmt'],
            'constituents_source': info.get('constituents_source', ''),
            'top_movers':          [],
            'news':                [],
        }

        # Stage 2: top movers within sector
        constituents = info.get('constituents', [])
        if constituents:
            print(f"  [hot_sectors] Stage 2: screening {len(constituents)} constituents...")
            const_data = batch_price_data(constituents)
            sorted_c = sorted(const_data.items(),
                              key=lambda x: abs(x[1]['pct']), reverse=True)[:3]
            hm['top_movers'] = [{'ticker': t, **d} for t, d in sorted_c]

        hot.append(hm)

    return hot

def fetch_ticker_news(ticker, max_items=3):
    """Fetch top news headlines for a ticker via yfinance."""
    try:
        raw = yf.Ticker(ticker).news or []
        items = []
        for n in raw[:max_items]:
            title = n.get('title', '')
            link  = n.get('link') or n.get('url', '')
            if title and link:
                items.append(SimpleNamespace(title=title, link=link, summary=None))
        return items
    except Exception as e:
        print(f"  [ticker_news] Failed for {ticker}: {e}")
        return []

# ── RSS helpers ───────────────────────────────────────────────────────────────
MIN_CONTENT_LENGTH = 80

def fetch_feed(url):
    try:
        ua = UserAgent()
        headers = {'User-Agent': ua.random.strip()}
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            return feedparser.parse(resp.text)
        print(f"  [rss] HTTP {resp.status_code} for {url}")
    except Exception as e:
        print(f"  [rss] Fetch failed ({url}): {e}")
    return None

def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup.find_all(['script', 'style', 'img', 'a', 'video', 'audio', 'iframe', 'input']):
        tag.decompose()
    return soup.get_text()

def clean_summary(text):
    if not text:
        return text
    lines = [l for l in text.splitlines()
             if not any(p in l for p in ['Thought:', 'thought:', '```', '.txt text'])]
    return '\n'.join(lines).strip().replace('\n', '<br>\n')

# ── Gemini API wrappers ───────────────────────────────────────────────────────
def chat_with_gemini(prompt, models=None, max_retries=2):
    """Try each model in chain; on quota/rate error switch immediately; on other errors retry."""
    if not _gemini_client:
        raise ValueError("GEMINI_API_KEY not set")
    chain = models or [DEFAULT_MODEL]
    for i, model_name in enumerate(chain):
        for attempt in range(max_retries + 1):
            try:
                response = _gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if i > 0:
                    print(f"  Fell back to model: {model_name}")
                return response.text
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ('quota', 'rate', '429', 'resource_exhausted')):
                    print(f"  Quota/rate limit on {model_name}, trying next model...")
                    break
                if attempt < max_retries:
                    wait = 2 ** attempt
                    print(f"  Gemini error on {model_name} (attempt {attempt + 1}): {e}, retry in {wait}s")
                    time.sleep(wait)
                else:
                    print(f"  Failed on {model_name} after {max_retries + 1} attempts: {e}")
                    if i == len(chain) - 1:
                        raise
                    break
    raise RuntimeError("All Gemini models exhausted")

def score_entries(titles, topic=None, models=None):
    """Score a batch of news titles 1-10. Returns list of floats."""
    if not titles:
        return []
    numbered = '\n'.join(f'{i + 1}. {t}' for i, t in enumerate(titles))
    hint     = f'（板块主题：{topic}）' if topic else ''
    prompt   = (
        f'以下是{len(titles)}条财经新闻标题{hint}。'
        f'请综合评估每条标题与板块主题的相关性及新闻重要性，评分1-10（10=极重要且高度相关）。'
        f'只输出JSON：{{"scores": [分数1, 分数2, ...]}}，不要输出任何其他内容。\n\n{numbered}'
    )
    try:
        raw   = chat_with_gemini(prompt, models=models or SCORE_MODEL_CHAIN)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            scores = json.loads(match.group()).get('scores', [])
            if len(scores) == len(titles):
                return [float(s) for s in scores]
    except Exception as e:
        print(f"  score_entries failed: {e}")
    return [5.0] * len(titles)

def translate_titles(titles, models=None):
    """Translate a batch of titles to Chinese. Returns list or None on failure."""
    if not titles:
        return titles
    numbered = '\n'.join(f'{i + 1}. {t}' for i, t in enumerate(titles))
    prompt   = (
        f'请将以下{len(titles)}条英文/日文财经新闻标题翻译成中文。遵守以下规则：\n'
        f'1. 品牌名、公司名、产品名保留英文原文，不得翻译（例如：lululemon、Apple、Tesla、Nvidia）。\n'
        f'2. 英文人名使用双语格式：保留英文原名并附上中文互联网常见译名，格式为"英文名（中文译名）"（例如：Elon Musk（马斯克））。\n'
        f'3. 日文人名使用双语格式：保留汉字原名并附上平假名读音，格式为"汉字名（平假名）"（例如：石破茂（いしばしげる））。\n'
        f'必须严格输出JSON数组，恰好{len(titles)}个元素：{{"titles": ["翻译1", "翻译2", ...]}}，'
        f'不要输出任何其他内容。\n\n{numbered}'
    )
    try:
        raw   = chat_with_gemini(prompt, models=models or TRANSLATE_MODEL_CHAIN)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            translated = json.loads(match.group()).get('titles', [])
            if len(translated) == len(titles):
                return [str(t).strip() for t in translated]
            elif translated:
                result = list(titles)
                for k, t in enumerate(translated[:len(titles)]):
                    result[k] = str(t).strip()
                print(f"  translate_titles: partial {len(translated)}/{len(titles)}")
                return result
    except Exception as e:
        print(f"  translate_titles failed: {e}")
    return None

def ai_summary(text, models=None):
    """Generate bilingual keywords + Chinese summary for a news article."""
    prompt = (
        f'{text}\n\n'
        f'以上为财经新闻内容，请用中文生成摘要和关键词。'
        f'规则：品牌名、公司名、产品名保留英文原文；英文人名使用"英文名（中文译名）"格式；日文人名使用"汉字名（平假名）"格式。'
        f'严格按以下格式输出两行，不得包含任何其他内容：\n'
        f'关键词：[提取{KEYWORD_LENGTH}个关键词，逗号分隔]\n'
        f'总结：[用中文详细概括文章要点，字数不少于80字，最多{SUMMARY_LENGTH}字]\n\n'
        f'只输出以上两行纯文本。禁止输出思考过程、Markdown语法或代码块。'
    )
    return clean_summary(chat_with_gemini(prompt, models=models or SUMMARY_MODEL_CHAIN))

def analyze_watchlist(items, run_type='morning', models=None):
    """Single Gemini call to analyse all watchlist tickers. Returns dict keyed by ticker."""
    if not items:
        return {}

    parts = []
    for item in items:
        part = (
            f"\n【{item['ticker']}】{item.get('name', item['ticker'])}\n"
            f"今日价格：{item['price_fmt']}，涨跌：{item['change_pct_fmt']}\n"
        )
        if item.get('news_titles'):
            part += '相关新闻：\n' + '\n'.join(f'  - {t}' for t in item['news_titles'][:3]) + '\n'
        parts.append(part)

    if run_type == 'morning':
        context_hint = (
            '【当前时间：东京07:30 — 早报】美欧市场已收盘，日本市场即将开盘（09:00 JST）。\n'
            '分析角度：美欧相关标的做隔夜收盘复盘；日本/亚洲相关标的做今日开盘前瞻。\n\n'
        )
    else:
        context_hint = (
            '【当前时间：东京22:00 — 晚报】日本市场已收盘（15:30 JST），欧洲盘中，美股即将开盘（22:30 JST）。\n'
            '分析角度：日本相关标的做今日收盘复盘；美股/商品/FX做美股开盘前瞻；欧洲相关标的做盘中动态简析。\n\n'
        )

    ticker_list = json.dumps([i['ticker'] for i in items], ensure_ascii=False)
    prompt = (
        context_hint
        + '以下是各标的的价格表现和相关新闻：\n'
        + ''.join(parts)
        + '\n请对每个标的给出：\n'
          '1. 走势简析（结合时间背景、价格和新闻，50字以内，中文）\n'
          '2. 近期展望（bullish/bearish/neutral 三选一，并附一句中文理由）\n\n'
          '严格输出JSON，顺序与输入一致：\n'
          '{"analyses": [{"ticker": "...", "today": "...", "outlook": "bullish|bearish|neutral", "outlook_reason": "..."}]}\n'
          f'不要输出任何其他内容。ticker顺序：{ticker_list}'
    )
    try:
        raw   = chat_with_gemini(prompt, models=models or WATCHLIST_MODEL_CHAIN)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            analyses = json.loads(match.group()).get('analyses', [])
            return {a['ticker']: a for a in analyses if isinstance(a, dict)}
    except Exception as e:
        print(f"  analyze_watchlist failed: {e}")
    return {}

# ── News section processing ───────────────────────────────────────────────────
def process_news_section(urls, max_items, section_name, topic,
                         last_run_links, last_run_fps, current_run_fps, seen_links,
                         run_type='morning', morning_bench=None):
    """Fetch RSS, deduplicate, score, translate, summarise. Returns (entries, bench_items)."""
    candidates = []

    for url in urls:
        feed = fetch_feed(url)
        if not feed:
            continue
        for entry in feed.entries:
            if len(candidates) >= max_items * 8:
                break

            link = getattr(entry, 'link', '')
            if not link:
                continue
            if link in seen_links or link in last_run_links:
                continue
            if link in {c[0].link for c in candidates}:
                continue

            title = getattr(entry, 'title', None) or link[:80]

            # Skip articles older than 24 hours
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_ts = calendar.timegm(entry.published_parsed)
                now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                if now_ts - pub_ts > 86400:
                    continue

            # Extract article text
            try:
                article = entry.content[0].value
            except Exception:
                article = getattr(entry, 'description', title)
            cleaned = clean_html(article or title)
            if len(cleaned) < MIN_CONTENT_LENGTH:
                cleaned = title

            # Semantic dedup
            fp = text_fingerprint(title, cleaned)
            if is_duplicate(fp, last_run_fps) or is_duplicate(fp, current_run_fps):
                continue

            entry.title   = title
            entry.article = cleaned
            candidates.append((entry, fp, cleaned))

    # Evening re-pool: inject morning bench candidates
    if run_type == 'evening' and morning_bench:
        bench_list  = morning_bench.get(section_name, [])
        bench_links = {e.link for e, _, _ in candidates}
        for item in bench_list:
            if item['link'] in seen_links or item['link'] in last_run_links:
                continue
            if item['link'] in bench_links:
                continue
            fake = SimpleNamespace(title=item['title'], link=item['link'],
                                   article=item['article'], summary=None)
            candidates.append((fake, item['fp'], item['article']))
            bench_links.add(item['link'])

    if not candidates:
        return [], []

    # Score
    if GEMINI_API_KEY and SCORE_MODEL_CHAIN:
        scores = score_entries([e.title for e, _, _ in candidates], topic=topic)
        order  = sorted(range(len(candidates)), key=lambda i: -scores[i])
        time.sleep(3)
    else:
        order = list(range(len(candidates)))

    # Intra-batch dedup
    deduped, ibfps = [], []
    for i in order:
        _, fp, _ = candidates[i]
        if not is_duplicate(fp, ibfps, threshold=INTRA_BATCH_THRESHOLD):
            deduped.append(i)
            ibfps.append(fp)
    order = deduped

    # Save bench (morning only: ranked-out candidates)
    bench_items = []
    if run_type == 'morning' and len(order) > max_items:
        for i in order[max_items:]:
            e, fp_val, art = candidates[i]
            bench_items.append({
                'link': e.link, 'title': e.title,
                'article': art, 'fp': fp_val,
                'published': getattr(e, 'published', ''),
            })

    order = order[:max_items]
    if TEST_MODE and not FULLTEST_MODE:
        order = order[:2]

    # Translate titles
    if GEMINI_API_KEY and TRANSLATE_MODEL_CHAIN and order:
        raw_titles = [candidates[i][0].title for i in order]
        translated = translate_titles(raw_titles)
        if translated:
            for rank, i in enumerate(order):
                candidates[i][0].title = translated[rank]
        time.sleep(3)

    # Summarise
    entries = []
    for i in order:
        entry, fp, cleaned = candidates[i]
        if GEMINI_API_KEY and SUMMARY_MODEL_CHAIN:
            try:
                entry.summary = ai_summary(cleaned)
                if not entry.summary or not entry.summary.strip():
                    entry.summary = cleaned[:200]
            except Exception as e:
                entry.summary = cleaned[:200]
                print(f"  Summarisation failed for [{entry.title}]: {e}")
            time.sleep(3)
        else:
            entry.summary = None

        entries.append(entry)
        seen_links.add(entry.link)
        current_run_fps.append(fp)

    print(f"  [{section_name}] candidates: {len(candidates)} -> selected: {len(entries)}")
    return entries, bench_items

# ── Bootstrap ─────────────────────────────────────────────────────────────────
os.makedirs(BASE, exist_ok=True)

run_type = get_run_type()
now = datetime.datetime.now(JST)

if UITEST_MODE:
    # ── UI Test: load cache, skip all network/AI calls ──────────────────────
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

    # ── Step 2: Hot sector detection (two-stage) ─────────────────────────────
    print("[hot_sectors] Detecting hot sectors...")
    hot_markets = detect_hot_sectors()
    if TEST_MODE:
        hot_markets = hot_markets[:2]

    for hm in hot_markets:
        hm['news'] = fetch_ticker_news(hm['etf'], max_items=HOT_MARKET_NEWS_MAX)
        print(f"  [hot_sectors] {hm['label']}: fetched {len(hm['news'])} news items")

    # ── Step 3: All Block-1 + Watchlist — single combined AI analysis ─────────
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
            'ticker':          hm['etf'],
            'name':            hm['label'],
            'news_titles':     [n.title for n in hm['news']] + mover_ctx,
            'analysis':        None,
            'outlook':         'neutral',
            'outlook_css':     'neutral',
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
            [i for i in indices_data     if i['price_fmt'] != 'N/A'] +
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
    if run_type == 'morning':
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

# ── Step 6: Render daily.html (web) and email HTML ───────────────────────────
_brief = 'Morning Brief' if run_type == 'morning' else 'Evening Brief'
if UITEST_MODE:
    edition = f'[UITEST] {_brief}'
elif FULLTEST_MODE:
    edition = f'[FULLTEST] {_brief}'
elif TEST_MODE:
    edition = f'[TEST] {_brief}'
else:
    edition = _brief

if run_type == 'morning':
    _news_s1_title = 'Morning Brief · Global Markets'
    _news_s1_sub   = 'US/EU overnight · Japan opens 09:00 JST'
    _news_s2_title = 'Morning Brief · Japan Markets'
    _news_s2_sub   = 'Open preview — 09:00 JST'
else:
    _news_s1_title = 'Evening Brief · Global Markets'
    _news_s1_sub   = 'EU open · US opens 22:30 JST'
    _news_s2_title = 'Evening Brief · Japan Markets'
    _news_s2_sub   = 'Session recap — closed 15:30 JST'

_render_ctx = dict(
    edition=edition,
    run_type=run_type,
    update_date=now.strftime('%Y-%m-%d'),
    update_time=now.strftime('%Y-%m-%d %H:%M:%S'),
    indices=indices_data,
    commodities=commodities_data,
    fx=fx_data,
    hist_dates=hist_dates,
    watchlist=watchlist_items,
    market_news=market_news_entries,
    japan_news=japan_news_entries,
    hot_markets=hot_markets,
    news_section_1_title=_news_s1_title,
    news_section_1_sub=_news_s1_sub,
    news_section_2_title=_news_s2_title,
    news_section_2_sub=_news_s2_sub,
)

daily_html_path = os.path.join(BASE, 'daily.html')
with open(daily_html_path, 'w', encoding='utf-8') as f:
    tmpl = Template(open('daily_template.html', encoding='utf-8').read())
    f.write(tmpl.render(**_render_ctx))
print(f"[output] daily.html -> {daily_html_path}")

email_html = Template(open('email_template.html', encoding='utf-8').read()).render(**_render_ctx)

# ── Step 7: Send email ────────────────────────────────────────────────────────
def send_daily_email():
    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = int(os.environ.get('SMTP_PORT') or '587')
    smtp_user = os.environ.get('SMTP_USER')
    smtp_pass = os.environ.get('SMTP_PASS')
    recipient = os.environ.get('RECIPIENT_EMAIL')

    if not all([smtp_host, smtp_user, smtp_pass, recipient]):
        print("[email] Not configured - set SMTP_HOST, SMTP_USER, SMTP_PASS, RECIPIENT_EMAIL.")
        return

    html_content = email_html

    if FULLTEST_MODE:
        subject = f'[FULLTEST] {edition} {now.strftime("%Y-%m-%d")}'
    elif TEST_MODE:
        subject = f'[TEST] {_brief} {now.strftime("%Y-%m-%d %H:%M")}'
    else:
        subject = f'{edition} {now.strftime("%Y-%m-%d")}'

    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = smtp_user
    msg['To']      = recipient
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
        print(f"[email] Digest sent to {recipient}")
    except Exception as e:
        print(f"[email] Failed to send: {e}")

if FORCE_EMAIL or not (TEST_MODE or FULLTEST_MODE or UITEST_MODE):
    send_daily_email()
else:
    print("[email] Skipped in test mode - use --email to force send")

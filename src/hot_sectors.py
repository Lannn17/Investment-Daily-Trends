"""Hot sector detection: batch price screening, two-stage ETF/constituent analysis, ticker news."""

from types import SimpleNamespace

import pandas as pd
import yfinance as yf

from .config import HOT_MARKET_THRESHOLD, SECTOR_UNIVERSE
from .price import format_price, price_arrow, price_css, ticker_url


# ── Batch price download ──────────────────────────────────────────────────────
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


# ── Two-stage hot sector detection ────────────────────────────────────────────
def detect_hot_sectors():
    """Stage 1: screen all sector ETFs. Stage 2: screen constituents of triggered sectors."""
    sectors = SECTOR_UNIVERSE.get('sectors', [])
    if not sectors:
        return []

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

        constituents = info.get('constituents', [])
        if constituents:
            print(f"  [hot_sectors] Stage 2: screening {len(constituents)} constituents...")
            const_data = batch_price_data(constituents)
            sorted_c = sorted(const_data.items(),
                              key=lambda x: abs(x[1]['pct']), reverse=True)[:3]
            movers = [{'ticker': t, **d} for t, d in sorted_c]
            for m in movers:
                m['name'] = _fetch_ticker_short_name(m['ticker'])
            hm['top_movers'] = movers

        hot.append(hm)

    return hot


# ── Ticker helpers ────────────────────────────────────────────────────────────
def _fetch_ticker_short_name(ticker):
    """Return an English display name for a ticker via yfinance."""
    try:
        info = yf.Ticker(ticker).info
        for key in ('shortName', 'longName'):
            name = (info.get(key) or '').strip()
            if name:
                non_ascii = sum(1 for c in name if ord(c) > 127)
                if non_ascii <= 2:
                    return name
        for key in ('shortName', 'longName'):
            name = (info.get(key) or '').strip()
            if name:
                return name
    except Exception:
        pass
    return ticker

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

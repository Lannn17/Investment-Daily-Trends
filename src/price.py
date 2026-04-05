"""Price data: formatting helpers, market session map, yfinance single/list fetch."""

import math
import datetime

import yfinance as yf

from .config import JST


# ── Formatting helpers ────────────────────────────────────────────────────────
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


# ── Market session hours by UTC offset ───────────────────────────────────────
# (exchange_name, open_local_hour, close_local_hour)
_MARKET_SESSIONS = {
    -5.0: ('NYSE/NASDAQ', 9.5,  16.0),  # EST
    -4.0: ('NYSE/NASDAQ', 9.5,  16.0),  # EDT
     9.0: ('TSE',         9.0,  15.5),  # JST
     8.0: ('HKEX/SGX',   9.0,  16.0),  # HKT/SGT
     0.0: ('LSE',         8.0,  16.5),  # GMT
     1.0: ('XETRA',       9.0,  17.5),  # CET
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

        hist5     = hist['Close'].tail(5)
        start5    = float(hist5.iloc[0])
        end5      = float(hist5.iloc[-1])
        change_5d = (end5 - start5) / start5 if start5 else 0.0

        # Determine as_of timestamp and market open/closed status
        try:
            ts      = hist.index[-1]
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_jst = datetime.datetime.now(JST)
            as_of       = ''
            market_name = ''
            market_open = False
            if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                tz_offset_h = ts.tzinfo.utcoffset(ts).total_seconds() / 3600
                session = _MARKET_SESSIONS.get(tz_offset_h)
                if session:
                    exch, open_h, close_h = session
                    market_name = exch
                    open_ts  = ts + datetime.timedelta(hours=open_h)
                    close_ts = ts + datetime.timedelta(hours=close_h)
                    if close_ts.astimezone(datetime.timezone.utc) <= now_utc:
                        as_of       = close_ts.astimezone(JST).strftime('%m/%d %H:%M')
                        market_open = False
                    elif open_ts.astimezone(datetime.timezone.utc) <= now_utc:
                        as_of       = now_jst.strftime('%m/%d %H:%M')
                        market_open = True
                    else:
                        as_of       = now_jst.strftime('%m/%d %H:%M')
                        market_open = False
                else:
                    as_of = ts.astimezone(JST).strftime('%m/%d')
            else:
                as_of = ts.replace(tzinfo=datetime.timezone.utc).astimezone(JST).strftime('%m/%d')
        except Exception:
            as_of       = ''
            market_name = ''
            market_open = False

        return {
            'ticker':         ticker,
            'label':          label,
            'url':            ticker_url(ticker),
            'price':          today,
            'price_fmt':      format_price(today),
            'change':         change,
            'change_fmt':     format_price(abs(change)),
            'change_pct':     change_pct,
            'change_pct_fmt': f'{change_pct * 100:+.2f}%',
            'change_arrow':   price_arrow(change),
            'css':            price_css(change),
            'history':        [format_price(float(v)) for v in hist5.values],
            'history_dates':  [d.strftime('%m/%d') for d in hist5.index],
            'change_5d':      change_5d,
            'change_5d_fmt':  f'{change_5d * 100:+.2f}%',
            'css5d':          price_css(change_5d),
            'as_of':          as_of,
            'market_name':    market_name,
            'market_open':    market_open,
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
        'as_of': '', 'market_name': '', 'market_open': False,
    }

def fetch_price_list(tickers, labels):
    items = []
    for ticker, label in zip(tickers, labels):
        item = fetch_price_item(ticker, label)
        items.append(item if item else _placeholder(ticker, label))
    return items

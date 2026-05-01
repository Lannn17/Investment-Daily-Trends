"""Configuration: CLI args, config.ini constants, model chains, watchlist, sector universe."""

import os
import json
import argparse
import configparser
import datetime

from dotenv import load_dotenv

load_dotenv('.env')

# ── CLI args ──────────────────────────────────────────────────────────────────
_ap = argparse.ArgumentParser()
_ap.add_argument('--test',     action='store_true', help='Quick test: 2 articles/section, state not saved')
_ap.add_argument('--fulltest', action='store_true', help='Full test: production count, state cleared after')
_ap.add_argument('--uitest',   action='store_true', help='UI test: skip all API/data calls, render from cache only')
_ap.add_argument('--email',    action='store_true', help='Force send email even in test/uitest mode')
_ap.add_argument('--edition',  choices=['morning', 'evening'], default=None)
_ap.add_argument('--demo',     action='store_true', help='Demo mode: isolated data in demo/, Japanese output, no email')
_args = _ap.parse_args()

TEST_MODE     = _args.test
FULLTEST_MODE = _args.fulltest
UITEST_MODE   = _args.uitest
FORCE_EMAIL   = _args.email
DEMO_MODE     = _args.demo
LANG          = 'ja' if DEMO_MODE else 'zh'

# ── config.ini ────────────────────────────────────────────────────────────────
_config = configparser.ConfigParser()
_config.read('config.ini')

def get_cfg(sec, key, default=None):
    val = _config.get(sec, key, fallback=default)
    return val.strip('"') if val else default

BASE                  = get_cfg('cfg', 'base', 'docs/')
if DEMO_MODE:
    BASE = 'demo/output/'

def _data_path(filename):
    """Return demo/<filename> if DEMO_MODE and the file exists there, else <filename>."""
    if DEMO_MODE:
        demo_path = os.path.join('demo', filename)
        if os.path.exists(demo_path):
            return demo_path
    return filename
SIMILARITY_THRESHOLD  = float(get_cfg('cfg', 'similarity_threshold',  '0.70'))
INTRA_BATCH_THRESHOLD = float(get_cfg('cfg', 'intra_batch_threshold', '0.60'))
KEYWORD_LENGTH        = int(get_cfg('cfg', 'keyword_length', '3'))
SUMMARY_LENGTH        = int(get_cfg('cfg', 'summary_length', '150'))
HOT_MARKET_THRESHOLD  = float(get_cfg('cfg', 'hot_market_threshold', '0.02'))
MARKET_NEWS_MAX       = int(get_cfg('cfg', 'market_news_max_items', '5'))
JAPAN_NEWS_MAX        = int(get_cfg('cfg', 'japan_news_max_items',  '3'))
HOT_MARKET_NEWS_MAX   = int(get_cfg('cfg', 'hot_market_news_max_items', '2'))

INDICES_TICKERS     = [t.strip() for t in get_cfg('indices',     'tickers', '').split(',') if t.strip()]
INDICES_LABELS      = [l.strip() for l in get_cfg('indices',     'labels',  '').split(',') if l.strip()]
COMMODITIES_TICKERS = [t.strip() for t in get_cfg('commodities', 'tickers', '').split(',') if t.strip()]
COMMODITIES_LABELS  = [l.strip() for l in get_cfg('commodities', 'labels',  '').split(',') if l.strip()]
FX_TICKERS          = [t.strip() for t in get_cfg('fx',          'tickers', '').split(',') if t.strip()]
FX_LABELS           = [l.strip() for l in get_cfg('fx',          'labels',  '').split(',') if l.strip()]

HOT_MARKET_ETFS     = [t.strip() for t in get_cfg('hot_markets', 'etfs',   '').split(',') if t.strip()]
HOT_MARKET_LABELS   = [l.strip() for l in get_cfg('hot_markets', 'labels', '').split(',') if l.strip()]

MARKET_NEWS_URLS    = [u.strip() for u in get_cfg('market_news', 'url', '').split(',') if u.strip()]
JAPAN_NEWS_URLS     = [u.strip() for u in get_cfg('japan_news',  'url', '').split(',') if u.strip()]

# ── Gemini model chains ───────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DEFAULT_MODEL  = os.environ.get('GEMINI_MODEL')   or 'gemini-3.1-flash-lite-preview'
FALLBACK_MODEL = os.environ.get('GEMINI_FALLBACK') or 'gemini-2.5-flash'

def _chain(*models):
    return [m.strip() for m in models if m and m.strip()]

SCORE_MODEL_CHAIN     = _chain(os.environ.get('SCORE_MODEL'),     DEFAULT_MODEL, FALLBACK_MODEL)
TRANSLATE_MODEL_CHAIN = _chain(os.environ.get('TRANSLATE_MODEL'), DEFAULT_MODEL, FALLBACK_MODEL)
SUMMARY_MODEL_CHAIN   = _chain(os.environ.get('SUMMARY_MODEL'),   DEFAULT_MODEL, FALLBACK_MODEL)
WATCHLIST_MODEL_CHAIN = _chain(os.environ.get('WATCHLIST_MODEL'), DEFAULT_MODEL, FALLBACK_MODEL)

print(f"[models] score={SCORE_MODEL_CHAIN} translate={TRANSLATE_MODEL_CHAIN} "
      f"summary={SUMMARY_MODEL_CHAIN} watchlist={WATCHLIST_MODEL_CHAIN}")

# ── Watchlist ─────────────────────────────────────────────────────────────────
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
        with open(_data_path('watchlist.json'), 'r', encoding='utf-8') as f:
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
        with open(_data_path('sector_universe.json'), 'r', encoding='utf-8') as f:
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

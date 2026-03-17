# Investment Daily Trends

Automated daily investment digest — price dashboard + market news, delivered via email and GitHub Pages.

## Features

- **Price Dashboard** (Block 1): Global indices, commodities, FX, and watchlist prices via yfinance — no AI cost
- **Market News** (Block 2): Yahoo Finance, CNBC, MarketWatch, Reuters, NHK RSS feeds with Gemini AI summaries
- **Hot Market Detection**: Screens 8 emerging-market ETFs daily; triggers news fetch if ±2% move detected
- **Watchlist AI Analysis**: Single combined Gemini call analyses all tickers (price + news context)
- **Morning/Evening editions**: 07:30 JST (US recap) and 22:00 JST (Japan close + US pre-market)
- **5-Day tab switch**: Web version (GitHub Pages) supports today / 5-day price table toggle

## Setup

### 1. Clone and install

```bash
pip install -r requirements.txt
```

### 2. Environment variables (GitHub Secrets)

| Secret | Description |
|--------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Override default model (optional) |
| `SCORE_MODEL` | Model for news scoring (optional) |
| `TRANSLATE_MODEL` | Model for title translation (optional) |
| `SUMMARY_MODEL` | Model for article summarisation (optional) |
| `WATCHLIST_MODEL` | Model for watchlist analysis (optional) |
| `SMTP_HOST` | SMTP server (e.g. smtp.gmail.com) |
| `SMTP_PORT` | SMTP port (default 587) |
| `SMTP_USER` | Sender email address |
| `SMTP_PASS` | Email app password |
| `RECIPIENT_EMAIL` | Recipient email address |

### 3. GitHub Pages

In repo Settings → Pages, set source to `docs/` folder on `main` branch.

### 4. Watchlist

Edit `watchlist.json` to add or remove tickers:

```json
{
  "tickers": ["IAU", "NEM", "NVDA", "TSM", "BRK-B", "LMT", "7203.T", "9984.T", "INDA"],
  "names": {
    "MY_TICKER": "My Custom Name"
  }
}
```

## Local test

```bash
# Quick test (2 articles/section, state not saved)
python main.py --test

# Force morning edition
python main.py --test --edition morning

# Full production test (state cleared after)
python main.py --fulltest
```

## Schedule

| Edition | JST | UTC |
|---------|-----|-----|
| Morning Brief | 07:30 | 22:30 (prev day) |
| Evening Brief | 22:00 | 13:00 |

## Data sources

- **Price data**: Yahoo Finance via yfinance (15-min delay intraday; exact at close)
- **Global news**: Yahoo Finance RSS, CNBC, MarketWatch, Reuters Business
- **Japan news**: NHK Business RSS, Japan Times Business RSS
- **Watchlist / hot market news**: yfinance ticker news API

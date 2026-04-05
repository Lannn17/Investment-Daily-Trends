# CLAUDE.md — Project Memory

Current version: v0.4.0

---

## Project Overview

Investment-Daily-Trends is an automated daily investment digest tool:
- Fetches price data for global indices, commodities, FX, and watchlist tickers via yfinance
- Fetches financial news from Yahoo Finance, CNBC, MarketWatch, Reuters, NHK RSS feeds
- Detects hot emerging markets via yfinance ETF daily move screening (±2% threshold)
- Uses Gemini AI to score, translate, and summarise news articles
- Uses a single Gemini call to analyse all watchlist tickers (price + news combined)
- Sends a daily HTML digest via Gmail SMTP (Morning 07:30 JST / Evening 22:00 JST)
- Runs on GitHub Actions; output served via GitHub Pages (docs/)

---

## Directory Structure

```
project-root/
├── .github/workflows/cron-job.yml
├── docs/
│   ├── last_run.json
│   └── morning_bench.json
├── main.py
├── requirements.txt
├── config.ini
├── watchlist.json
├── daily_template.html
├── README.md
├── CLAUDE.md          ← this file
└── CHANGELOG.md
```

---

## Rule 1: Language

- Variable names and function names in English
- Code comments and docstrings in English
- Ticker symbols always in English (e.g. NVDA, 7203.T)
- News summaries output in bilingual Chinese + English
- All documentation files in English with a brief Chinese summary

---

## Rule 2: Version Management

Follows Semantic Versioning: `vMAJOR.MINOR.PATCH`

| Type  | Trigger |
|-------|---------|
| PATCH | Small fixes, bug fixes |
| MINOR | New feature, new data source |
| MAJOR | Architecture refactor, breaking change |

- Current version recorded at top of this file
- Claude determines the version bump type autonomously — do not ask the user
- Update version at top of this file and add entry to CHANGELOG.md before every commit

---

## Rule 3: CHANGELOG.md

- Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format
- Each entry: version number, date, categories (Added / Changed / Fixed / Removed)
- Newest version always at top
- Written in English with a brief Chinese summary line

---

## Rule 4: Git Commit Format

- All commit messages in English
- Format: `<type>: <description> [vX.Y.Z]`
- Types: `feat`, `fix`, `docs`, `chore`

---

## Rule 5: Workflow Per Change

1. Modify code files
2. **Run `python main.py --test` and confirm exit code 0 before proceeding**
3. Determine version bump type (PATCH / MINOR / MAJOR)
4. Update version at top of this file
5. Add new entry to CHANGELOG.md
6. Commit with English message
7. Push to remote

---

## Key Design Decisions

- **Price data**: yfinance only — free, no API key, no AI cost
- **Watchlist AI analysis**: single combined Gemini call for all tickers to minimise API usage
- **Hot market detection**: yfinance ETF screening first, AI only if triggered
- **Email structure**: Block 1 = Price Dashboard, Block 2 = Market News (always separated)
- **Price table**: today-only view; 5-day tab removed as of v0.2.0
- **Block 1 AI analysis**: all indices, commodities, FX, and watchlist items analysed in one combined Gemini call
- **Gemini model**: gemini-3.1-flash-lite-preview (default); fallback models via env vars

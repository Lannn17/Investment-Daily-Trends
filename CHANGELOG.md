# Changelog

All notable changes to Investment-Daily-Trends will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v0.2.0] - 2026-03-17

### Added
- AI analysis (today trend + outlook) for all Block 1 items: indices, commodities, FX, watchlist
- All 21 items analysed in a single combined Gemini call (no extra API cost)
- Ticker hyperlinks on every price card linking to Yahoo Finance

### Changed
- Price dashboard redesigned: unified 4-column card grid (3-col tablet, 2-col mobile)
- Each ticker displayed as a compact square card with price, change, AI analysis, and outlook badge
- Removed 5-day tab and JavaScript tab switching; today-only view always shown

### 新增 / 变更
- 所有价格标的（指数、商品、外汇、自选）均增加AI走势分析，合并为单次Gemini调用
- 价格面板改为4列紧凑方块布局，手机端自适应2列；移除5日标签页

---

## [v0.1.0] - 2026-03-17

### Added
- Initial project setup
- Price dashboard: global indices, commodities, FX via yfinance (no AI cost)
- Market news block: Yahoo Finance, CNBC, MarketWatch, Reuters, NHK RSS feeds
- Hot market detection: yfinance ETF screening (±2% threshold triggers news fetch)
- Watchlist: config-based tickers (IAU, NEM, NVDA, TSM, BRK-B, LMT, 7203.T, 9984.T, INDA)
- Watchlist AI analysis: single Gemini call for all tickers combined
- Gemini API integration (gemini-3.1-flash-lite-preview default)
- Morning (07:30 JST) and Evening (22:00 JST) editions
- GitHub Actions cron workflow
- GitHub Pages deployment (docs/)
- Gmail SMTP daily digest email
- Cross-run deduplication via last_run.json and morning_bench.json
- Today / 5-day price table toggle on web version

### 新增
- 项目初始化，包含价格面板、市场新闻、热门市场、自选标的四大模块

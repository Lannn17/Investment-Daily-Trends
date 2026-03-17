# Changelog

All notable changes to Investment-Daily-Trends will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v0.3.2] - 2026-03-17

### Changed
- Hot Sectors Today extracted from Market News block into its own standalone section at the end of both `daily_template.html` and `email_template.html`
- Max triggered sectors increased from 3 to 5; TEST_MODE display limit increased from 1 to 2

### 变更
- 热门板块模块从市场新闻区独立出来，在两个模板末尾作为独立区块展示；测试模式最多展示2个，正常模式最多5个

---

## [v0.3.1] - 2026-03-17

### Added
- `email_template.html`: table-based email layout matching the mobile web design (2-col price grid, inline styles, no CSS Grid — Gmail compatible)
- `--email` CLI flag: explicit opt-in to send email in test/uitest modes; test runs no longer auto-send

### Changed
- Email now renders from `email_template.html` instead of `daily.html`
- `--test` / `--uitest` / `--fulltest` modes skip email by default

### 新增 / 变更
- 新增邮件模板（table布局，内联样式），兼容Gmail手机端，视觉效果与手机网页预览一致
- 新增 --email 参数，测试模式下默认不发邮件，需显式指定才发送

---

## [v0.3.0] - 2026-03-17

### Added
- Two-stage hot sector detection replacing the old fixed EM ETF list
- Stage 1: single `yf.download()` batch call screens 46 sector ETFs (US SPDR 11 sectors, 14 EM country ETFs, 12 Japan TOPIX-17 sectors, 9 commodity futures)
- Stage 2: for each triggered sector, batch downloads constituent stocks and surfaces top 3 movers
- `sector_universe.json`: curated constituent lists (~10–20 stocks per sector) with source attribution
- Source labels displayed in report for both sector ETF and constituent data
- `batch_price_data()` helper for efficient multi-ticker batch downloads via pandas MultiIndex

### Changed
- `detect_hot_markets()` replaced by `detect_hot_sectors()` with two-stage logic
- Hot markets section in template now shows sector ETF source, top 3 movers with price/change, and constituent source attribution
- AI analysis context enriched with top mover ticker + % change info

### 新增 / 变更
- 热门市场模块改为两阶段板块筛选：第一阶段批量下载46个板块ETF，第二阶段下载触发板块的成分股找出涨跌最大标的
- 新增 sector_universe.json 管理全球板块及成分股列表，报告中标注数据来源

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

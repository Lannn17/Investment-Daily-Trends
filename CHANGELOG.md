# Changelog

All notable changes to Investment-Daily-Trends will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v0.5.0] - 2026-04-06

### Added
- Portfolio tracking feature (`src/portfolio.py`): per-lot P&L computation with FX conversion to a base currency
- `portfolio.json` config file: supports multiple buy lots per position, `strategy` field (`speculative` / `dca`) to differentiate active trading vs systematic investing (e.g. NISA DCA)
- Portfolio AI analysis (`analyze_portfolio` in `src/ai_client.py`): strategy-aware Gemini advice — speculative positions receive per-lot breakdown with hold/add/cut recommendation; DCA positions receive long-term fundamental outlook
- Portfolio block in email and daily HTML: appears before Watchlist in the Price Dashboard; shows per-lot detail rows for speculative positions and AI advice badge per position
- `portfolio.json` added to `.gitignore` to keep personal holdings private

### 新增
- Portfolio 持仓追踪：支持逐笔买入记录，按 strategy 区分投机（speculative）和定投（dca）策略；AI 针对两种策略给出差异化投资建议；邮件和网页均展示 Portfolio 板块

---

## [v0.4.0] - 2026-04-06

### Changed
- Refactored monolithic `main.py` (~1088 lines) into modular `src/` package with 7 focused modules:
  - `src/config.py` — CLI args, config.ini constants, model chains, watchlist/sector universe
  - `src/state.py` — state persistence (last_run, morning_bench, render_cache) and dedup helpers
  - `src/price.py` — price formatting utilities and yfinance single/list fetch
  - `src/hot_sectors.py` — batch price screening and two-stage hot sector detection
  - `src/ai_client.py` — Gemini client and all AI functions (score/translate/summarise/analyse)
  - `src/news.py` — RSS fetch, HTML cleaning, and full news processing pipeline
  - `src/output.py` — HTML rendering and SMTP email delivery
- `main.py` reduced to a thin orchestration entry point (~247 lines)

### 修改
- 将单体 `main.py` 重构为模块化 `src/` 包，按功能拆分为7个独立模块，`main.py` 仅保留编排逻辑

## [v0.3.9] - 2026-03-23

### Added
- Weekend Edition: Saturday and Sunday evening runs now produce a "Daily Markets · Weekend" digest — prices labelled as Friday's last close, Hot Sectors block hidden (markets closed), news still included, yellow banner alerts readers to the weekend context
- Digest title renamed from "Morning/Evening Brief" to "Daily Markets · Morning/Evening/Weekend" to distinguish from other news digest projects

### Changed
- Morning cron restricted to weekdays only (`1-5`); evening cron unchanged (runs daily)

### 新增 / 修改
- 新增周末版本：周六、周日晚间推送"Daily Markets · Weekend"，价格标注为周五收盘价，热门板块跳过，顶部显示黄色提示横幅
- 摘要标题由"Morning/Evening Brief"改为"Daily Markets · Morning/Evening/Weekend"
- 早报 cron 限制为工作日（周一至周五），晚报保持每日运行

---

## [v0.3.8] - 2026-03-23

### Added
- Hot Sectors top movers now display the company's English short name next to the ticker symbol, making emerging-market and sector tickers (e.g. `003550.KS`, `5020.T`) immediately identifiable

### 新增
- 热门板块涨跌股票旁新增英文公司简称，便于不熟悉新兴市场代码的读者快速识别

---

## [v0.3.7] - 2026-03-19

### Added
- Market status badge on each price card: shows exchange name (NYSE/NASDAQ, TSE, LSE, etc.) and whether the market was OPEN or CLOSED at digest fetch time

### Fixed
- Price card `as_of` no longer shows a future timestamp. Logic: market closed → confirmed close time (JST); market open → current fetch time; pre-open → current fetch time

### 新增 / 修复
- 价格卡片新增交易所状态标签（如 NYSE/NASDAQ · CLOSED），直观显示抓取时刻该市场是否开盘
- 修复晚报美股标的时间显示"未来时间"（如 03/19 05:00）的问题

---

## [v0.3.6] - 2026-03-18

### Fixed
- Translation prompts (`translate_titles`, `ai_summary`) now preserve brand/company/product names in English instead of translating them to Chinese
- English person names rendered as `English Name（中文译名）`; Japanese person names rendered as `漢字名（ひらがな）`

### 修复
- 翻译提示词更新：品牌名、公司名、产品名保留英文；英文人名附中文译名；日文人名附平假名注音

---

## [v0.3.5] - 2026-03-18

### Added
- "Copy for AI" button in the web page footer — copies the full digest context (price dashboard with AI analyses, all news summaries, hot sectors) as plain text to clipboard, ready to paste into any AI chat

### 新增
- 网页底部新增「Copy for AI」按钮，一键复制当日日报内容（价格分析、新闻摘要、热点板块）至剪贴板，方便粘贴至任意 AI 对话继续追问

---

## [v0.3.4] - 2026-03-18

### Fixed
- `GEMINI_MODEL` env var set to empty string (e.g. via absent GitHub Secret) now correctly falls back to the hardcoded default model instead of producing an empty model chain and silently skipping all AI calls
- Removed unused model-override secrets (`GEMINI_MODEL`, `SCORE_MODEL`, `TRANSLATE_MODEL`, `SUMMARY_MODEL`, `WATCHLIST_MODEL`) from `cron-job.yml` — these were never set and caused empty-string injection into the env

### 修复
- `GEMINI_MODEL` 为空字符串时正确回退至默认模型；移除工作流中从未设置的冗余 model secret 引用

---

## [v0.3.3] - 2026-03-17

### Added
- Price cards now show exchange close time (JST) next to each ticker — computed from bar timestamp + per-exchange close offset
- News section headers are now context-aware: "Morning Brief · Global Markets" vs "Evening Brief · Global Markets", with JST timing sub-label
- AI analysis prompt is now run-type aware: morning prompt focuses on US/EU overnight recap + Japan open preview; evening prompt focuses on Japan session recap + US pre-market outlook
- News scoring topics vary by run type to surface the most relevant articles for each edition

### Changed
- Report title (`edition`) and email subject now always include "Morning Brief" / "Evening Brief" in test/uitest modes (was "Daily Brief")

### 新增 / 变更
- 价格标的显示交易所收盘时间（JST）；新闻区标题区分早晚报；AI分析提示词按早晚报角度调整；报告标题在测试模式下也区分早晚

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

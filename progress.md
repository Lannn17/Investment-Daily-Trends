# Portfolio Enhancement Progress

## Feature List

| ID | Feature | Status |
|----|---------|--------|
| P1-A | FX拆分三列 (Stock/FX/JPY計) + portfolio day return | ✅ done |
| P1-C | 模板更新：Summary bar + 新列 + FX汇率摘要行 | ✅ done |
| P2-A | Benchmark Alpha 对比 | ✅ done |
| P2-B | Risk Alerts (新闻×持仓 AI关联) | ✅ done |
| P3   | 多账户分组显示 | ✅ done |

---

## Key Files

- `src/portfolio.py` — 持仓计算核心
- `src/ai_client.py` — Gemini AI 调用
- `main.py` — 主流程 (Step 3.5 / Step 4.5)
- `daily_template.html` — 网页模板
- `email_template.html` — 邮件模板
- `portfolio.json` — 持仓配置（含 lots[]，支持 per-lot P&L）

## Current portfolio.json Schema
```json
{
  "base_currency": "JPY",
  "positions": [
    {
      "ticker": "NVDA",
      "strategy": "speculative|dca",
      "cost_currency": "USD",
      "lots": [{"shares": 20, "cost": 90.00, "date": "2024-01-15"}]
    }
  ]
}
```

## Current compute_portfolio() Output (per position)
ticker, name, strategy, cost_ccy, total_shares, avg_cost/fmt,
current_price/fmt, day_change_pct/fmt/css, pnl_pct/fmt/css,
value_base, pnl_base, lots[], action, advice, error, weight/fmt

## Current portfolio_data Output
base_currency, positions[], total_value/fmt, total_cost,
total_pnl/fmt, total_pnl_pct/fmt, total_css

---

## Checkpoints

### P1-A + P2-A ✅ (2026-04-06)

**What changed:**
- `src/portfolio.py` — full rewrite:
  - `fetch_fx_pairs(currencies, base_ccy)`: fetches 5d yfinance history for each ccy pair, returns `{ccy: {rate, prev_rate, day_change, rate_fmt, day_change_fmt, css}}`
  - `compute_portfolio()`: now uses price_cache, calls fetch_fx_pairs once upfront, computes per-position `price_effect / fx_effect / total_base_return`, `prev_value_base`; portfolio-level `day_return = (total_value - total_prev_value) / total_prev_value`; new output fields: `day_return/fmt/css`, `fx_rates`, `benchmark_tickers`, `benchmarks: []`, `risk_alerts: []`; position-level: `needs_fx`, `price_effect/fmt/css`, `fx_effect/fmt/css`, `total_base_return/fmt/css`, `prev_value_base`, `account`
  - `compute_benchmarks(portfolio_data, indices_data)`: mutates `portfolio_data['benchmarks']` in place; matches `benchmark_tickers`, computes `alpha = port_ret - bench_ret`
- `main.py`: added `compute_benchmarks` to import; added `compute_benchmarks(portfolio_data, indices_data)` call after compute_portfolio in Step 3.5
- `portfolio.json`: added `"benchmarks": ["^GSPC", "^N225"]`

**Next: P1-C** — update `daily_template.html` and `email_template.html`
- Summary bar: day_return + total_pnl + benchmark alpha
- FX rate row in position table
- Replace "今日" column with 3 columns: Stock% / FX% / JPY計%

### P1-C ✅ (2026-04-06)

**What changed:**
- `daily_template.html` portfolio section (lines ~234-296) replaced:
  - Summary bar: today's day_return + total_pnl_pct + total_value + benchmark alpha per bench
  - Table: 8 cols (标的/持仓/现价/Stock%/FX%/JPY計%/盈亏/占比); price_effect_fmt / fx_effect_fmt / total_base_return_fmt
  - Totals row: day_return + total_pnl_pct + total_value
  - Benchmark alpha rows after totals
  - FX rate summary div after table
  - colspan updated 6→8 for per-lot rows and AI advice rows
- `email_template.html` portfolio section (lines ~74-129) same changes with inline color styles
- `python main.py --test` passes (exit 0)

**Next: P2-B** — analyze_portfolio_risk() in ai_client.py + Step 4.5 in main.py + risk_alerts template section
**Then: P3** — multi-account grouping in templates

### P2-B ✅ (2026-04-06)

**What changed:**
- `src/ai_client.py`: added `analyze_portfolio_risk(portfolio_data, news_entries)` — cross-references holdings vs top-20 news titles, returns `[{ticker, name, alert}]`
- `main.py`: added `analyze_portfolio_risk` to import; added Step 4.5 after japan_news, calls analyze_portfolio_risk and writes result to `portfolio_data['risk_alerts']`
- `daily_template.html`: added Risk Alerts block (yellow warning box) after FX rates
- `email_template.html`: same Risk Alerts block with inline styles
- `python main.py --test` and `--uitest` both pass

**Next: P3** — optional `account` field + multi-account grouping in templates

### P3 ✅ (2026-04-06)

**What changed:**
- `portfolio.json`: added `"account"` field to all positions (NVDA/IAU → "SBI証券"; 7203.T → "NISA")
- `daily_template.html` + `email_template.html`: replaced `{% for p in portfolio.positions %}` with `{% for acct, acct_positions in portfolio.positions | groupby('account') %}`, shows account header row when any position has non-empty account; backward compatible (no header shown if all accounts empty)
- Both `--uitest` and `--test` pass

**All features complete.** ✅

---

## Demo Mode (v0.7.0) — In Progress

### Goal
展示用デモモード。個人データなし・日本語AI出力・GitHub Pages配信。

### 実装済み ✅

| File | 変更内容 |
|------|---------|
| `src/config.py` | `--demo` CLI引数、`DEMO_MODE`/`LANG` グローバル、`BASE` オーバーライド (`demo/output/`)、`_data_path()` ヘルパー、`load_watchlist()`/`load_sector_universe()` に適用 |
| `src/ai_client.py` | `LANG` インポート、`PROMPTS = {'zh':..., 'ja':...}` 辞書追加、`score_entries` / `translate_titles` / `ai_summary` / `analyze_watchlist` / `analyze_portfolio_risk` の5関数を `PROMPTS[LANG]` から取得するよう全リファクタ |
| `src/portfolio.py` | `load_portfolio()` を `_data_path('portfolio.json')` に変更 |
| `main.py` | `DEMO_MODE`/`LANG` インポート、ニューストピック文字列を `_NEWS_TOPICS[LANG]` で zh/ja 切り替え、メール送信をデモ時スキップ |
| `demo/watchlist.json` | 新規作成（9銘柄: MSFT/GOOGL/AMZN/TSM/BRK-B/LMT/7203.T/9984.T/INDA） |
| `demo/portfolio.json` | 新規作成（6ポジション: NVDA/AAPL/VOO/7203.T/9984.T/IAU、2アカウント） |
| `.github/workflows/demo.yml` | 新規作成（手動 + UTC 22:30 スケジュール、GitHub Pages デプロイ） |
| `.gitignore` | `demo/output/` と `watchlist.json` を追加 |

### 未実施 ⏳

- `python main.py --demo --test` で動作確認（exit 0 確認）
- `CLAUDE.md` バージョン v0.6.0 → v0.7.0 更新
- `CHANGELOG.md` エントリ追加
- git commit & push

### 既知のギャップ

- `analyze_portfolio()` のプロンプトは中国語のまま（仕様書でスコープ外と明記）→ デモ時もポートフォリオ投資アドバイス欄は中国語で出力される
- GitHub Pages を有効にするには Settings → Pages → Source: GitHub Actions の設定が必要

### 将来の計画

| 優先度 | タスク |
|--------|--------|
| 高 | `analyze_portfolio()` も日本語化（PROMPTS に追加） |
| 中 | `demo/sector_universe.json` を作成し、デモ用ホットセクター定義を分離 |
| 低 | `daily_template.html` / `email_template.html` の固定テキスト（セクションタイトル等）を `lang` 変数で zh/ja 切り替え |
| 低 | fund_scraper.py — 日本の投資信託（eMAXIS 等）の基準価額スクレイピング |

# 后续功能补充

## 经济日历 / 重要事件提醒
思路：抓取当日及未来2-3天的重要经济数据发布和央行事件
数据源：Investing.com Economic Calendar、FRED API、或 pandas_datareader
在邮件顶部增加一个「今日/明日关注」卡片：
🇺🇸 20:30 非农就业数据（前值: +175K，预期: +180K）
🇯🇵 08:50 日银会议纪要

code block:
def fetch_economic_calendar(days_ahead=2):
    """抓取未来N天的重要经济事件"""
    events = []
    # 方案A: 爬取 investing.com/economic-calendar
    # 方案B: 使用 tradingeconomics API (免费tier)
    # 方案C: 维护一个简单的 JSON 手动日历 + 自动补充
    
    # 按重要性过滤 (高/中)
    # 按时间排序
    # 标注与 watchlist 相关的事件
    return events

## 技术指标信号面板
为 watchlist 和主要指数添加简单的技术信号
利用已有的 yfinance 数据，扩展获取更长历史（50天/200天）
计算：
RSI (14) → 超买(>70) / 超卖(<30) 提醒
MA交叉 → 50日均线 vs 200日均线（金叉/死叉）
布林带位置 → 价格触及上轨/下轨
在价格表格中加一列信号图标：🔴 超买、🟢 超卖、⚡ 金叉等

code block:
import numpy as np

def compute_technicals(ticker, period='6mo'):
    """计算关键技术指标"""
    hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    close = hist['Close']
    
    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # Moving averages
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    
    # Bollinger Bands
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    
    current = close.iloc[-1]
    signals = []
    
    if rsi.iloc[-1] > 70:
        signals.append(('RSI超买', 'bearish'))
    elif rsi.iloc[-1] < 30:
        signals.append(('RSI超卖', 'bullish'))
    
    if ma50.iloc[-1] > ma200.iloc[-1] and ma50.iloc[-2] <= ma200.iloc[-2]:
        signals.append(('金叉', 'bullish'))
    elif ma50.iloc[-1] < ma200.iloc[-1] and ma50.iloc[-2] >= ma200.iloc[-2]:
        signals.append(('死叉', 'bearish'))
    
    if current >= bb_upper.iloc[-1]:
        signals.append(('触及布林上轨', 'bearish'))
    elif current <= bb_lower.iloc[-1]:
        signals.append(('触及布林下轨', 'bullish'))
    
    return {
        'rsi': round(rsi.iloc[-1], 1),
        'ma50': round(ma50.iloc[-1], 2),
        'ma200': round(ma200.iloc[-1], 2),
        'bb_position': round((current - bb_lower.iloc[-1]) / 
                             (bb_upper.iloc[-1] - bb_lower.iloc[-1]) * 100, 0),
        'signals': signals,
    }

## Fear & Greed 情绪指标
集成市场情绪指数，一目了然判断市场温度
VIX（恐慌指数）：已经可以通过 yfinance ^VIX 获取
CNN Fear & Greed Index：可爬取或用 API
Put/Call Ratio：CBOE 数据
在邮件顶部用一个温度计/仪表盘可视化展示

code block:
def fetch_sentiment_indicators():
    """获取市场情绪指标"""
    sentiment = {}
    
    # VIX
    vix = yf.Ticker('^VIX').history(period='5d')
    if not vix.empty:
        vix_val = float(vix['Close'].iloc[-1])
        sentiment['vix'] = {
            'value': round(vix_val, 2),
            'level': 'extreme_fear' if vix_val > 30 else 
                     'fear' if vix_val > 20 else
                     'neutral' if vix_val > 15 else 'greed',
            'change': float(vix['Close'].iloc[-1] - vix['Close'].iloc[-2]),
        }
    
    # CNN Fear & Greed (爬虫)
    try:
        resp = requests.get('https://production.dataviz.cnn.io/index/fearandgreed/graphdata',
                          headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if resp.ok:
            data = resp.json()
            score = data.get('fear_and_greed', {}).get('score', 50)
            sentiment['fear_greed'] = {
                'score': round(score),
                'label': _fg_label(score),
            }
    except Exception:
        pass
    
    return sentiment

def _fg_label(score):
    if score <= 25: return 'Extreme Fear'
    if score <= 45: return 'Fear'
    if score <= 55: return 'Neutral'
    if score <= 75: return 'Greed'
    return 'Extreme Greed'

## Portfolio 模拟追踪
支持用户配置持仓和成本价，追踪盈亏
新增 portfolio.json 配置文件：
json
{
  "positions": [
    {"ticker": "NVDA", "shares": 50, "avg_cost": 120.00, "currency": "USD"},
    {"ticker": "7203.T", "shares": 100, "avg_cost": 2800, "currency": "JPY"},
    {"ticker": "IAU", "shares": 200, "avg_cost": 45.50, "currency": "USD"}
  ],
  "base_currency": "JPY",
  "fx_rates_override": {}
}
每日计算：
各持仓当日盈亏（金额 + 百分比）
总组合价值变化
组合权重饼图数据

plan:
核心思路
新增 portfolio.json 配置持仓
每次跑日报时自动计算盈亏
在邮件里加一个 Portfolio 板块，放在 watchlist 附近
1. portfolio.json
json
{
  "base_currency": "JPY",
  "positions": [
    {
      "ticker": "NVDA",
      "shares": 50,
      "avg_cost": 120.00,
      "cost_currency": "USD"
    },
    {
      "ticker": "7203.T",
      "shares": 100,
      "avg_cost": 2800,
      "cost_currency": "JPY"
    },
    {
      "ticker": "IAU",
      "shares": 200,
      "avg_cost": 45.50,
      "cost_currency": "USD"
    }
  ]
}
cost_currency 大多数情况和标的交易货币一致，写明确一点不容易出错。

2. 主要代码
python
# ── Portfolio tracking ────────────────────────────────────────────────────────

def load_portfolio():
    try:
        with open('portfolio.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not load portfolio.json: {e}")
        return None


def get_fx_rate(from_ccy, to_ccy):
    """获取汇率，同币种返回1.0"""
    if from_ccy == to_ccy:
        return 1.0
    pair = f'{from_ccy}{to_ccy}=X'
    try:
        hist = yf.Ticker(pair).history(period='2d')
        if not hist.empty:
            return float(hist['Close'].dropna().iloc[-1])
    except Exception as e:
        print(f"  [fx_rate] {pair} failed: {e}")
    return None


def compute_portfolio(portfolio_cfg, price_cache=None):
    """
    计算持仓盈亏。
    price_cache: dict {ticker: price_item} 可复用已有的 watchlist/indices 数据避免重复请求
    """
    if not portfolio_cfg:
        return None

    base_ccy = portfolio_cfg.get('base_currency', 'JPY')
    positions = portfolio_cfg.get('positions', [])
    if not positions:
        return None

    # 收集需要的汇率
    fx_cache = {}
    results = []
    total_cost_base = 0.0
    total_value_base = 0.0

    for pos in positions:
        ticker = pos['ticker']
        shares = pos['shares']
        avg_cost = pos['avg_cost']
        cost_ccy = pos.get('cost_currency', 'USD')

        # 取当前价格 — 优先用已有缓存
        current_price = None
        day_change_pct = 0.0
        if price_cache and ticker in price_cache:
            cached = price_cache[ticker]
            current_price = cached.get('price')
            day_change_pct = cached.get('change_pct', 0.0)
        
        if current_price is None:
            item = fetch_price_item(ticker, ticker)
            if item and item['price'] is not None:
                current_price = item['price']
                day_change_pct = item['change_pct']

        if current_price is None:
            results.append({
                'ticker': ticker,
                'name': WATCHLIST_NAMES.get(ticker, ticker),
                'shares': shares,
                'avg_cost': avg_cost,
                'error': True,
            })
            continue

        # 汇率: cost_ccy -> base_ccy
        if cost_ccy not in fx_cache:
            fx_cache[cost_ccy] = get_fx_rate(cost_ccy, base_ccy)
        fx_rate = fx_cache[cost_ccy]
        if fx_rate is None:
            fx_rate = 1.0  # fallback

        # 计算（同币种计算盈亏，再转 base）
        cost_total = avg_cost * shares
        value_total = current_price * shares
        pnl = value_total - cost_total
        pnl_pct = pnl / cost_total if cost_total else 0.0

        cost_base = cost_total * fx_rate
        value_base = value_total * fx_rate
        pnl_base = value_base - cost_base

        total_cost_base += cost_base
        total_value_base += value_base

        results.append({
            'ticker': ticker,
            'name': WATCHLIST_NAMES.get(ticker, ticker),
            'shares': shares,
            'avg_cost': avg_cost,
            'current_price': current_price,
            'price_fmt': format_price(current_price),
            'cost_ccy': cost_ccy,
            'day_change_pct': day_change_pct,
            'day_change_fmt': f'{day_change_pct * 100:+.2f}%',
            'day_css': price_css(day_change_pct),
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'pnl_pct_fmt': f'{pnl_pct * 100:+.2f}%',
            'pnl_css': price_css(pnl),
            'value_base': value_base,
            'pnl_base': pnl_base,
            'error': False,
        })

    # 组合总计
    total_pnl_base = total_value_base - total_cost_base
    total_pnl_pct = total_pnl_base / total_cost_base if total_cost_base else 0.0

    # 权重
    for r in results:
        if not r.get('error') and total_value_base > 0:
            r['weight'] = r['value_base'] / total_value_base
            r['weight_fmt'] = f'{r["weight"] * 100:.1f}%'
        else:
            r['weight'] = 0
            r['weight_fmt'] = '-'

    return {
        'base_currency': base_ccy,
        'positions': results,
        'total_value': total_value_base,
        'total_value_fmt': f'{total_value_base:,.0f}',
        'total_cost': total_cost_base,
        'total_pnl': total_pnl_base,
        'total_pnl_fmt': f'{total_pnl_base:+,.0f}',
        'total_pnl_pct': total_pnl_pct,
        'total_pnl_pct_fmt': f'{total_pnl_pct * 100:+.2f}%',
        'total_css': price_css(total_pnl_base),
    }
3. 接入 main.py
在你现有的 Step 3（watchlist 之后）加几行就行：

python
# ── Step 3.5: Portfolio ──────────────────────────────────────────────────
print("[portfolio] Computing positions...")
portfolio_cfg = load_portfolio()

# 复用已经拉过的价格，避免重复请求
_price_cache = {}
for item in watchlist_items + indices_data + commodities_data + fx_data:
    if item.get('price') is not None:
        _price_cache[item['ticker']] = item

portfolio_data = compute_portfolio(portfolio_cfg, price_cache=_price_cache)
然后 _render_ctx 里加上：

python
portfolio=portfolio_data,
save_render_cache / load_render_cache 也相应加上 portfolio 字段。

4. 邮件模板里的呈现
邮件 HTML 里大概这样一块就够了，风格和你现有的价格表统一：

html
{% if portfolio %}
<table class="price-table" style="width:100%; border-collapse:collapse; margin:16px 0;">
  <caption style="text-align:left; font-size:16px; font-weight:bold; padding:8px 0;">
    Portfolio · {{ portfolio.base_currency }}
    <span class="{{ portfolio.total_css }}" style="font-size:14px; margin-left:12px;">
      {{ portfolio.total_pnl_fmt }} ({{ portfolio.total_pnl_pct_fmt }})
    </span>
  </caption>
  <tr style="background:#f5f5f5; font-size:12px;">
    <th style="padding:6px; text-align:left;">标的</th>
    <th style="padding:6px; text-align:right;">持仓</th>
    <th style="padding:6px; text-align:right;">现价</th>
    <th style="padding:6px; text-align:right;">今日</th>
    <th style="padding:6px; text-align:right;">盈亏</th>
    <th style="padding:6px; text-align:right;">占比</th>
  </tr>
  {% for p in portfolio.positions %}
  {% if not p.error %}
  <tr style="border-bottom:1px solid #eee;">
    <td style="padding:6px;">{{ p.name }}</td>
    <td style="padding:6px; text-align:right; color:#888;">{{ p.shares }}</td>
    <td style="padding:6px; text-align:right;">{{ p.price_fmt }}</td>
    <td style="padding:6px; text-align:right;" class="{{ p.day_css }}">{{ p.day_change_fmt }}</td>
    <td style="padding:6px; text-align:right;" class="{{ p.pnl_css }}">{{ p.pnl_pct_fmt }}</td>
    <td style="padding:6px; text-align:right; color:#888;">{{ p.weight_fmt }}</td>
  </tr>
  {% endif %}
  {% endfor %}
  <tr style="border-top:2px solid #333; font-weight:bold;">
    <td style="padding:6px;">合计</td>
    <td></td>
    <td></td>
    <td></td>
    <td style="padding:6px; text-align:right;" class="{{ portfolio.total_css }}">
      {{ portfolio.total_pnl_pct_fmt }}
    </td>
    <td style="padding:6px; text-align:right;">{{ portfolio.total_value_fmt }}</td>
  </tr>
</table>
{% endif %}
整体结构
text
邮件里的顺序:
┌─ Edition header ──────────────┐
├─ Indices / Commodities / FX   │  ← 已有
├─ Hot Sectors                  │  ← 已有
├─ Portfolio 💰                 │  ← 新增：就这一块
├─ Watchlist                    │  ← 已有
├─ Market News                  │  ← 已有
├─ Japan News                   │  ← 已有
└───────────────────────────────┘

## AI对话窗口
"""Gemini AI client: scoring, translation, summarisation, watchlist analysis."""

import re
import json
import time

from google import genai

from .config import (
    GEMINI_API_KEY, DEFAULT_MODEL,
    SCORE_MODEL_CHAIN, TRANSLATE_MODEL_CHAIN,
    SUMMARY_MODEL_CHAIN, WATCHLIST_MODEL_CHAIN,
    KEYWORD_LENGTH, SUMMARY_LENGTH,
)

# ── Client init ───────────────────────────────────────────────────────────────
_gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


# ── Core API wrapper ──────────────────────────────────────────────────────────
def chat_with_gemini(prompt, models=None, max_retries=2):
    """Try each model in chain; on quota/rate error switch immediately; on other errors retry."""
    if not _gemini_client:
        raise ValueError("GEMINI_API_KEY not set")
    chain = models or [DEFAULT_MODEL]
    for i, model_name in enumerate(chain):
        for attempt in range(max_retries + 1):
            try:
                response = _gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if i > 0:
                    print(f"  Fell back to model: {model_name}")
                return response.text
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ('quota', 'rate', '429', 'resource_exhausted')):
                    print(f"  Quota/rate limit on {model_name}, trying next model...")
                    break
                if attempt < max_retries:
                    wait = 2 ** attempt
                    print(f"  Gemini error on {model_name} (attempt {attempt + 1}): {e}, retry in {wait}s")
                    time.sleep(wait)
                else:
                    print(f"  Failed on {model_name} after {max_retries + 1} attempts: {e}")
                    if i == len(chain) - 1:
                        raise
                    break
    raise RuntimeError("All Gemini models exhausted")


# ── Scoring ───────────────────────────────────────────────────────────────────
def score_entries(titles, topic=None, models=None):
    """Score a batch of news titles 1-10. Returns list of floats."""
    if not titles:
        return []
    numbered = '\n'.join(f'{i + 1}. {t}' for i, t in enumerate(titles))
    hint     = f'（板块主题：{topic}）' if topic else ''
    prompt   = (
        f'以下是{len(titles)}条财经新闻标题{hint}。'
        f'请综合评估每条标题与板块主题的相关性及新闻重要性，评分1-10（10=极重要且高度相关）。'
        f'只输出JSON：{{"scores": [分数1, 分数2, ...]}}，不要输出任何其他内容。\n\n{numbered}'
    )
    try:
        raw   = chat_with_gemini(prompt, models=models or SCORE_MODEL_CHAIN)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            scores = json.loads(match.group()).get('scores', [])
            if len(scores) == len(titles):
                return [float(s) for s in scores]
    except Exception as e:
        print(f"  score_entries failed: {e}")
    return [5.0] * len(titles)


# ── Translation ───────────────────────────────────────────────────────────────
def translate_titles(titles, models=None):
    """Translate a batch of titles to Chinese. Returns list or None on failure."""
    if not titles:
        return titles
    numbered = '\n'.join(f'{i + 1}. {t}' for i, t in enumerate(titles))
    prompt   = (
        f'请将以下{len(titles)}条英文/日文财经新闻标题翻译成中文。遵守以下规则：\n'
        f'1. 品牌名、公司名、产品名保留英文原文，不得翻译（例如：lululemon、Apple、Tesla、Nvidia）。\n'
        f'2. 英文人名使用双语格式：保留英文原名并附上中文互联网常见译名，格式为"英文名（中文译名）"（例如：Elon Musk（马斯克））。\n'
        f'3. 日文人名使用双语格式：保留汉字原名并附上平假名读音，格式为"汉字名（平假名）"（例如：石破茂（いしばしげる））。\n'
        f'必须严格输出JSON数组，恰好{len(titles)}个元素：{{"titles": ["翻译1", "翻译2", ...]}}，'
        f'不要输出任何其他内容。\n\n{numbered}'
    )
    try:
        raw   = chat_with_gemini(prompt, models=models or TRANSLATE_MODEL_CHAIN)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            translated = json.loads(match.group()).get('titles', [])
            if len(translated) == len(titles):
                return [str(t).strip() for t in translated]
            elif translated:
                result = list(titles)
                for k, t in enumerate(translated[:len(titles)]):
                    result[k] = str(t).strip()
                print(f"  translate_titles: partial {len(translated)}/{len(titles)}")
                return result
    except Exception as e:
        print(f"  translate_titles failed: {e}")
    return None


# ── Summarisation ─────────────────────────────────────────────────────────────
def _clean_summary(text):
    if not text:
        return text
    lines = [l for l in text.splitlines()
             if not any(p in l for p in ['Thought:', 'thought:', '```', '.txt text'])]
    return '\n'.join(lines).strip().replace('\n', '<br>\n')

def ai_summary(text, models=None):
    """Generate bilingual keywords + Chinese summary for a news article."""
    prompt = (
        f'{text}\n\n'
        f'以上为财经新闻内容，请用中文生成摘要和关键词。'
        f'规则：品牌名、公司名、产品名保留英文原文；英文人名使用"英文名（中文译名）"格式；日文人名使用"汉字名（平假名）"格式。'
        f'严格按以下格式输出两行，不得包含任何其他内容：\n'
        f'关键词：[提取{KEYWORD_LENGTH}个关键词，逗号分隔]\n'
        f'总结：[用中文详细概括文章要点，字数不少于80字，最多{SUMMARY_LENGTH}字]\n\n'
        f'只输出以上两行纯文本。禁止输出思考过程、Markdown语法或代码块。'
    )
    return _clean_summary(chat_with_gemini(prompt, models=models or SUMMARY_MODEL_CHAIN))


# ── Watchlist analysis ────────────────────────────────────────────────────────
def analyze_watchlist(items, run_type='morning', models=None):
    """Single Gemini call to analyse all watchlist tickers. Returns dict keyed by ticker."""
    if not items:
        return {}

    parts = []
    for item in items:
        part = (
            f"\n【{item['ticker']}】{item.get('name', item['ticker'])}\n"
            f"今日价格：{item['price_fmt']}，涨跌：{item['change_pct_fmt']}\n"
        )
        if item.get('news_titles'):
            part += '相关新闻：\n' + '\n'.join(f'  - {t}' for t in item['news_titles'][:3]) + '\n'
        parts.append(part)

    if run_type == 'morning':
        context_hint = (
            '【当前时间：东京07:30 — 早报】美欧市场已收盘，日本市场即将开盘（09:00 JST）。\n'
            '分析角度：美欧相关标的做隔夜收盘复盘；日本/亚洲相关标的做今日开盘前瞻。\n\n'
        )
    else:
        context_hint = (
            '【当前时间：东京22:00 — 晚报】日本市场已收盘（15:30 JST），欧洲盘中，美股即将开盘（22:30 JST）。\n'
            '分析角度：日本相关标的做今日收盘复盘；美股/商品/FX做美股开盘前瞻；欧洲相关标的做盘中动态简析。\n\n'
        )

    ticker_list = json.dumps([i['ticker'] for i in items], ensure_ascii=False)
    prompt = (
        context_hint
        + '以下是各标的的价格表现和相关新闻：\n'
        + ''.join(parts)
        + '\n请对每个标的给出：\n'
          '1. 走势简析（结合时间背景、价格和新闻，50字以内，中文）\n'
          '2. 近期展望（bullish/bearish/neutral 三选一，并附一句中文理由）\n\n'
          '严格输出JSON，顺序与输入一致：\n'
          '{"analyses": [{"ticker": "...", "today": "...", "outlook": "bullish|bearish|neutral", "outlook_reason": "..."}]}\n'
          f'不要输出任何其他内容。ticker顺序：{ticker_list}'
    )
    try:
        raw   = chat_with_gemini(prompt, models=models or WATCHLIST_MODEL_CHAIN)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            analyses = json.loads(match.group()).get('analyses', [])
            return {a['ticker']: a for a in analyses if isinstance(a, dict)}
    except Exception as e:
        print(f"  analyze_watchlist failed: {e}")
    return {}


# ── Portfolio analysis ────────────────────────────────────────────────────────
def analyze_portfolio(portfolio_data, run_type='morning', models=None):
    """
    Single Gemini call to analyse portfolio positions and generate investment advice.
    Differentiates between speculative (per-lot focus) and dca (long-term focus).
    Returns dict keyed by ticker: {action, reason}.
    """
    if not portfolio_data:
        return {}

    positions = [p for p in portfolio_data.get('positions', []) if not p.get('error')]
    if not positions:
        return {}

    parts = []
    for pos in positions:
        if pos['strategy'] == 'dca':
            part = (
                f"\n【{pos['ticker']}】{pos['name']} [策略：定投/NISA]\n"
                f"总持仓：{pos['total_shares']}股，均价：{pos['avg_cost_fmt']} {pos['cost_ccy']}\n"
                f"当前价：{pos['price_fmt']}，今日涨跌：{pos['day_change_fmt']}\n"
                f"总盈亏：{pos['pnl_pct_fmt']}，组合占比：{pos['weight_fmt']}\n"
            )
        else:
            part = (
                f"\n【{pos['ticker']}】{pos['name']} [策略：投机/主动]\n"
                f"当前价：{pos['price_fmt']}，今日涨跌：{pos['day_change_fmt']}\n"
                f"各批次持仓：\n"
            )
            for i, lot in enumerate(pos['lots'], 1):
                part += (
                    f"  批次{i}：{lot['shares']}股 @{lot['cost_fmt']} {pos['cost_ccy']}"
                    f"（{lot['date']}）盈亏 {lot['pnl_pct_fmt']}\n"
                )
            part += f"总盈亏：{pos['pnl_pct_fmt']}，组合占比：{pos['weight_fmt']}\n"
        parts.append(part)

    base_ccy = portfolio_data['base_currency']
    prompt = (
        f'以下是我的投资组合（基准货币：{base_ccy}），'
        f'总资产：{portfolio_data["total_value_fmt"]} {base_ccy}，'
        f'总盈亏：{portfolio_data["total_pnl_pct_fmt"]}。\n\n'
        + ''.join(parts)
        + '\n请对每个持仓给出投资建议，规则如下：\n'
          '- dca（定投）类：重点分析长期基本面，判断是否适合继续定投，忽略短期波动\n'
          '- speculative（投机）类：针对各批次盈亏状态，给出具体操作建议\n\n'
          'action 只能从以下四个选一个：hold（持有）/ add（加仓）/ cut（减仓）/ monitor（观察）\n\n'
          '严格输出JSON，不要输出任何其他内容：\n'
          '{"advice": [{"ticker": "...", "action": "hold|add|cut|monitor", "reason": "...（50字以内中文）"}]}'
    )

    try:
        raw   = chat_with_gemini(prompt, models=models or WATCHLIST_MODEL_CHAIN)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            advice = json.loads(match.group()).get('advice', [])
            return {a['ticker']: a for a in advice if isinstance(a, dict)}
    except Exception as e:
        print(f"  analyze_portfolio failed: {e}")
    return {}


# ── Portfolio risk alerts ──────────────────────────────────────────────────────
def analyze_portfolio_risk(portfolio_data, news_entries, models=None):
    """
    Cross-reference portfolio holdings with recent news to surface relevant alerts.
    news_entries: combined list of market_news + japan_news entry objects (have .title).
    Returns list of dicts: [{ticker, name, alert}] — only items with actual hits.
    """
    if not portfolio_data or not news_entries:
        return []

    positions = [p for p in portfolio_data.get('positions', []) if not p.get('error')]
    if not positions:
        return []

    # Build holdings summary
    holdings_lines = []
    for pos in positions:
        holdings_lines.append(f"  - {pos['ticker']} ({pos['name']})")
    holdings_text = '\n'.join(holdings_lines)

    # Collect news titles (cap at 20 to keep prompt short)
    titles = [getattr(e, 'title', str(e)) for e in news_entries[:20]]
    if not titles:
        return []
    news_text = '\n'.join(f'{i+1}. {t}' for i, t in enumerate(titles))

    ticker_list = json.dumps([p['ticker'] for p in positions], ensure_ascii=False)
    prompt = (
        f'以下是我的持仓列表：\n{holdings_text}\n\n'
        f'以下是今日财经新闻标题（共{len(titles)}条）：\n{news_text}\n\n'
        f'请找出与持仓直接相关的新闻（行业政策、监管、竞争对手重大动态、宏观风险等），'
        f'并生成简短的风险/机会提醒（30字以内中文）。\n'
        f'只输出与持仓确实相关的条目，无相关则返回空数组。\n'
        f'严格输出JSON，不要输出任何其他内容：\n'
        f'{{"alerts": [{{"ticker": "持仓代码", "alert": "提醒内容"}}]}}\n'
        f'合法的ticker值只能来自此列表：{ticker_list}'
    )

    try:
        raw   = chat_with_gemini(prompt, models=models or WATCHLIST_MODEL_CHAIN)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            alerts = json.loads(match.group()).get('alerts', [])
            valid_tickers = {p['ticker'] for p in positions}
            result = []
            for a in alerts:
                if not isinstance(a, dict):
                    continue
                ticker = a.get('ticker', '')
                alert  = a.get('alert', '').strip()
                if ticker in valid_tickers and alert:
                    name = next((p['name'] for p in positions if p['ticker'] == ticker), ticker)
                    result.append({'ticker': ticker, 'name': name, 'alert': alert})
            return result
    except Exception as e:
        print(f"  analyze_portfolio_risk failed: {e}")
    return []

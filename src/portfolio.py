"""Portfolio tracking: load config, compute per-lot P&L, FX breakdown, day return."""

import json

import yfinance as yf

from .config import WATCHLIST_NAMES, _data_path
from .price import fetch_price_item, format_price, price_css


def load_portfolio():
    """Load portfolio.json. Returns dict or None if missing/invalid."""
    try:
        with open(_data_path('portfolio.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Warning: could not load portfolio.json: {e}")
        return None


def fetch_fx_pairs(currencies, base_ccy):
    """Fetch today + yesterday FX rates for each foreign currency vs base.

    Returns dict: {ccy: {rate, prev_rate, day_change, rate_fmt, day_change_fmt, css}}
    Same-currency entries get rate=1, day_change=0.
    """
    result = {}
    for ccy in currencies:
        if ccy == base_ccy:
            result[ccy] = {
                'rate': 1.0, 'prev_rate': 1.0, 'day_change': 0.0,
                'rate_fmt': '1.0000', 'day_change_fmt': '-', 'css': 'flat',
            }
            continue
        pair = f'{ccy}{base_ccy}=X'
        try:
            hist = yf.Ticker(pair).history(period='5d', auto_adjust=True)
            hist = hist[hist['Close'].notna()]
            if len(hist) >= 2:
                rate      = float(hist['Close'].iloc[-1])
                prev_rate = float(hist['Close'].iloc[-2])
                chg       = (rate - prev_rate) / prev_rate if prev_rate else 0.0
            elif len(hist) == 1:
                rate = prev_rate = float(hist['Close'].iloc[0])
                chg  = 0.0
            else:
                print(f"  [fx_pairs] No data for {pair}")
                continue
            result[ccy] = {
                'rate':           rate,
                'prev_rate':      prev_rate,
                'day_change':     chg,
                'rate_fmt':       format_price(rate),
                'day_change_fmt': f'{chg * 100:+.2f}%',
                'css':            price_css(chg),
            }
        except Exception as e:
            print(f"  [fx_pairs] Failed {pair}: {e}")
    return result


def compute_portfolio(portfolio_cfg, price_cache=None):
    """
    Compute P&L for all positions using per-lot cost records.
    Adds FX breakdown (price_effect / fx_effect / total_base_return) and
    portfolio-level day return.

    price_cache: dict {ticker: price_item} reuses already-fetched prices.
    Returns dict with positions and totals, or None if no valid config.
    """
    if not portfolio_cfg:
        return None

    base_ccy  = portfolio_cfg.get('base_currency', 'JPY')
    positions = portfolio_cfg.get('positions', [])
    bench_tkrs = portfolio_cfg.get('benchmarks', [])
    if not positions:
        return None

    # Fetch FX data for all unique foreign currencies upfront
    currencies = list(set(p.get('cost_currency', 'USD') for p in positions))
    print(f"  [portfolio] Fetching FX pairs: {[c for c in currencies if c != base_ccy]}")
    fx_pairs = fetch_fx_pairs(currencies, base_ccy)

    results          = []
    total_cost_base  = 0.0
    total_value_base = 0.0
    total_prev_value = 0.0

    for pos in positions:
        ticker   = pos['ticker']
        strategy = pos.get('strategy', 'speculative')
        cost_ccy = pos.get('cost_currency', 'USD')
        lots     = pos.get('lots', [])
        account  = pos.get('account', '')

        if not lots:
            continue

        # ── Current price ────────────────────────────────────────────────
        current_price  = None
        day_change_pct = 0.0

        if price_cache and ticker in price_cache:
            cached         = price_cache[ticker]
            current_price  = cached.get('price')
            day_change_pct = cached.get('change_pct', 0.0)

        if current_price is None:
            item = fetch_price_item(ticker, ticker)
            if item and item['price'] is not None:
                current_price  = item['price']
                day_change_pct = item.get('change_pct', 0.0)

        if current_price is None:
            results.append({
                'ticker':   ticker,
                'name':     WATCHLIST_NAMES.get(ticker, ticker),
                'strategy': strategy,
                'account':  account,
                'lots':     [],
                'error':    True,
            })
            continue

        # ── FX rate & breakdown ──────────────────────────────────────────
        fx        = fx_pairs.get(cost_ccy, {'rate': 1.0, 'prev_rate': 1.0, 'day_change': 0.0})
        fx_rate   = fx['rate']
        fx_prev   = fx['prev_rate']
        needs_fx  = (cost_ccy != base_ccy)
        fx_effect = fx['day_change'] if needs_fx else 0.0

        # total_base_return = (1+price_effect) × (1+fx_effect) − 1
        price_effect      = day_change_pct
        total_base_return = (1 + price_effect) * (1 + fx_effect) - 1 if needs_fx else price_effect

        # ── Per-lot P&L ──────────────────────────────────────────────────
        lot_results      = []
        pos_total_shares = 0
        pos_total_cost   = 0.0
        pos_total_value  = 0.0

        for lot in lots:
            shares = lot['shares']
            cost   = lot['cost']
            date   = lot.get('date', '')

            lot_cost_total  = cost * shares
            lot_value_total = current_price * shares
            lot_pnl         = lot_value_total - lot_cost_total
            lot_pnl_pct     = lot_pnl / lot_cost_total if lot_cost_total else 0.0

            lot_results.append({
                'shares':      shares,
                'cost':        cost,
                'cost_fmt':    format_price(cost),
                'date':        date,
                'pnl_pct':     lot_pnl_pct,
                'pnl_pct_fmt': f'{lot_pnl_pct * 100:+.2f}%',
                'pnl_css':     price_css(lot_pnl_pct),
            })

            pos_total_shares += shares
            pos_total_cost   += lot_cost_total
            pos_total_value  += lot_value_total

        pos_pnl     = pos_total_value - pos_total_cost
        pos_pnl_pct = pos_pnl / pos_total_cost if pos_total_cost else 0.0
        avg_cost    = pos_total_cost / pos_total_shares if pos_total_shares else 0.0

        cost_base  = pos_total_cost  * fx_rate
        value_base = pos_total_value * fx_rate
        pnl_base   = value_base - cost_base

        # Previous day value (for portfolio day return)
        prev_price      = current_price / (1 + price_effect) if price_effect != -1.0 else current_price
        prev_value_base = prev_price * pos_total_shares * fx_prev

        total_cost_base  += cost_base
        total_value_base += value_base
        total_prev_value += prev_value_base

        results.append({
            'ticker':         ticker,
            'name':           WATCHLIST_NAMES.get(ticker, ticker),
            'strategy':       strategy,
            'account':        account,
            'cost_ccy':       cost_ccy,
            'needs_fx':       needs_fx,
            'total_shares':   pos_total_shares,
            'avg_cost':       avg_cost,
            'avg_cost_fmt':   format_price(avg_cost),
            'current_price':  current_price,
            'price_fmt':      format_price(current_price),
            # Legacy day change fields (keep for existing template rows)
            'day_change_pct': day_change_pct,
            'day_change_fmt': f'{day_change_pct * 100:+.2f}%',
            'day_css':        price_css(day_change_pct),
            # FX breakdown
            'price_effect':           price_effect,
            'price_effect_fmt':       f'{price_effect * 100:+.2f}%',
            'price_effect_css':       price_css(price_effect),
            'fx_effect':              fx_effect,
            'fx_effect_fmt':          f'{fx_effect * 100:+.2f}%' if needs_fx else '-',
            'fx_effect_css':          price_css(fx_effect) if needs_fx else 'flat',
            'total_base_return':      total_base_return,
            'total_base_return_fmt':  f'{total_base_return * 100:+.2f}%',
            'total_base_return_css':  price_css(total_base_return),
            # Total P&L (native ccy)
            'pnl_pct':        pos_pnl_pct,
            'pnl_pct_fmt':    f'{pos_pnl_pct * 100:+.2f}%',
            'pnl_css':        price_css(pos_pnl_pct),
            # Base-ccy values
            'value_base':     value_base,
            'pnl_base':       pnl_base,
            'prev_value_base': prev_value_base,
            # Placeholders
            'lots':           lot_results,
            'action':         'monitor',
            'advice':         '',
            'weight':         0.0,
            'weight_fmt':     '-',
            'error':          False,
        })

    valid = [r for r in results if not r.get('error')]
    if not valid:
        return None

    # ── Portfolio totals ──────────────────────────────────────────────────────
    total_pnl_base = total_value_base - total_cost_base
    total_pnl_pct  = total_pnl_base / total_cost_base if total_cost_base else 0.0

    # Portfolio day return (base ccy weighted)
    day_return     = (total_value_base - total_prev_value) / total_prev_value if total_prev_value > 0 else 0.0

    for r in valid:
        r['weight']     = r['value_base'] / total_value_base if total_value_base else 0.0
        r['weight_fmt'] = f'{r["weight"] * 100:.1f}%'

    # FX rate summary (only foreign currencies)
    fx_rates_display = {
        ccy: info for ccy, info in fx_pairs.items() if ccy != base_ccy
    }

    return {
        'base_currency':      base_ccy,
        'positions':          results,
        'benchmark_tickers':  bench_tkrs,
        # Day return
        'day_return':         day_return,
        'day_return_fmt':     f'{day_return * 100:+.2f}%',
        'day_return_css':     price_css(day_return),
        # Total
        'total_value':        total_value_base,
        'total_value_fmt':    f'{total_value_base:,.0f}',
        'total_cost':         total_cost_base,
        'total_pnl':          total_pnl_base,
        'total_pnl_fmt':      f'{total_pnl_base:+,.0f}',
        'total_pnl_pct':      total_pnl_pct,
        'total_pnl_pct_fmt':  f'{total_pnl_pct * 100:+.2f}%',
        'total_css':          price_css(total_pnl_base),
        # FX summary
        'fx_rates':           fx_rates_display,
        # Filled by compute_benchmarks()
        'benchmarks':         [],
        # Filled by analyze_portfolio_risk()
        'risk_alerts':        [],
    }


def compute_benchmarks(portfolio_data, indices_data):
    """Compare portfolio daily return vs benchmark indices.
    Mutates portfolio_data['benchmarks'] in place.
    """
    if not portfolio_data:
        return
    bench_tkrs = portfolio_data.get('benchmark_tickers', [])
    port_ret   = portfolio_data['day_return']

    comparisons = []
    for item in indices_data:
        if item['ticker'] not in bench_tkrs:
            continue
        bench_ret = item.get('change_pct')
        if bench_ret is None:
            continue
        alpha = port_ret - bench_ret
        comparisons.append({
            'label':      item.get('label', item['ticker']),
            'ticker':     item['ticker'],
            'return':     bench_ret,
            'return_fmt': item.get('change_pct_fmt', f'{bench_ret * 100:+.2f}%'),
            'alpha':      alpha,
            'alpha_fmt':  f'{alpha * 100:+.2f}%',
            'alpha_css':  price_css(alpha),
        })

    portfolio_data['benchmarks'] = comparisons

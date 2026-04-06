"""Portfolio tracking: load config, compute per-lot P&L, FX conversion."""

import json

import yfinance as yf

from .config import WATCHLIST_NAMES
from .price import fetch_price_item, format_price, price_css


def load_portfolio():
    """Load portfolio.json. Returns dict or None if missing/invalid."""
    try:
        with open('portfolio.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Warning: could not load portfolio.json: {e}")
        return None


def get_fx_rate(from_ccy, to_ccy):
    """Fetch exchange rate from_ccy -> to_ccy via yfinance. Returns float or None."""
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
    Compute P&L for all positions using per-lot cost records.
    price_cache: dict {ticker: price_item} reuses already-fetched prices.
    Returns dict with positions and totals, or None if no valid config.
    """
    if not portfolio_cfg:
        return None

    base_ccy  = portfolio_cfg.get('base_currency', 'JPY')
    positions = portfolio_cfg.get('positions', [])
    if not positions:
        return None

    fx_cache         = {}
    results          = []
    total_cost_base  = 0.0
    total_value_base = 0.0

    for pos in positions:
        ticker   = pos['ticker']
        strategy = pos.get('strategy', 'speculative')
        cost_ccy = pos.get('cost_currency', 'USD')
        lots     = pos.get('lots', [])

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
                day_change_pct = item['change_pct']

        if current_price is None:
            results.append({
                'ticker':   ticker,
                'name':     WATCHLIST_NAMES.get(ticker, ticker),
                'strategy': strategy,
                'lots':     [],
                'error':    True,
            })
            continue

        # ── FX rate: cost_ccy -> base_ccy ────────────────────────────────
        if cost_ccy not in fx_cache:
            fx_cache[cost_ccy] = get_fx_rate(cost_ccy, base_ccy)
        fx_rate = fx_cache[cost_ccy] or 1.0

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

        total_cost_base  += cost_base
        total_value_base += value_base

        results.append({
            'ticker':         ticker,
            'name':           WATCHLIST_NAMES.get(ticker, ticker),
            'strategy':       strategy,
            'cost_ccy':       cost_ccy,
            'total_shares':   pos_total_shares,
            'avg_cost':       avg_cost,
            'avg_cost_fmt':   format_price(avg_cost),
            'current_price':  current_price,
            'price_fmt':      format_price(current_price),
            'day_change_pct': day_change_pct,
            'day_change_fmt': f'{day_change_pct * 100:+.2f}%',
            'day_css':        price_css(day_change_pct),
            'pnl_pct':        pos_pnl_pct,
            'pnl_pct_fmt':    f'{pos_pnl_pct * 100:+.2f}%',
            'pnl_css':        price_css(pos_pnl_pct),
            'value_base':     value_base,
            'pnl_base':       pnl_base,
            'lots':           lot_results,
            'action':         'monitor',
            'advice':         '',
            'error':          False,
        })

    if not results or all(r.get('error') for r in results):
        return None

    # ── Portfolio totals ──────────────────────────────────────────────────────
    total_pnl_base = total_value_base - total_cost_base
    total_pnl_pct  = total_pnl_base / total_cost_base if total_cost_base else 0.0

    for r in results:
        if not r.get('error') and total_value_base > 0:
            r['weight']     = r['value_base'] / total_value_base
            r['weight_fmt'] = f'{r["weight"] * 100:.1f}%'
        else:
            r['weight']     = 0.0
            r['weight_fmt'] = '-'

    return {
        'base_currency':     base_ccy,
        'positions':         results,
        'total_value':       total_value_base,
        'total_value_fmt':   f'{total_value_base:,.0f}',
        'total_cost':        total_cost_base,
        'total_pnl':         total_pnl_base,
        'total_pnl_fmt':     f'{total_pnl_base:+,.0f}',
        'total_pnl_pct':     total_pnl_pct,
        'total_pnl_pct_fmt': f'{total_pnl_pct * 100:+.2f}%',
        'total_css':         price_css(total_pnl_base),
    }

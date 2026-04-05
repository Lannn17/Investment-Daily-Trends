"""State persistence: last_run, morning_bench, render_cache. Dedup helpers."""

import os
import json
from difflib import SequenceMatcher
from types import SimpleNamespace

from .config import BASE, SIMILARITY_THRESHOLD, INTRA_BATCH_THRESHOLD


# ── last_run (news dedup across runs) ─────────────────────────────────────────
def load_last_run():
    try:
        with open(os.path.join(BASE, 'last_run.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get('links', [])), data.get('fingerprints', [])
    except Exception:
        return set(), []

def save_last_run(links, fingerprints):
    try:
        with open(os.path.join(BASE, 'last_run.json'), 'w', encoding='utf-8') as f:
            json.dump({'links': list(links), 'fingerprints': fingerprints},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: could not save last_run: {e}")


# ── morning_bench (carry-over candidates to evening) ──────────────────────────
def load_morning_bench():
    try:
        with open(os.path.join(BASE, 'morning_bench.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_morning_bench(bench):
    try:
        with open(os.path.join(BASE, 'morning_bench.json'), 'w', encoding='utf-8') as f:
            json.dump(bench, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: could not save morning_bench: {e}")


# ── render_cache (--uitest skips all API calls) ───────────────────────────────
def _entry_to_dict(e):
    """Convert SimpleNamespace news entry to plain dict for JSON serialisation."""
    return e.__dict__ if hasattr(e, '__dict__') else dict(e)

def save_render_cache(ctx):
    try:
        cache = {}
        for key, val in ctx.items():
            if key in ('market_news', 'japan_news'):
                cache[key] = [_entry_to_dict(e) for e in val]
            elif key == 'hot_markets':
                cache[key] = [
                    {**{k: v for k, v in hm.items() if k != 'news'},
                     'news': [_entry_to_dict(n) for n in hm.get('news', [])]}
                    for hm in val
                ]
            else:
                cache[key] = val
        with open(os.path.join(BASE, 'render_cache.json'), 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: could not save render_cache: {e}")

def load_render_cache():
    with open(os.path.join(BASE, 'render_cache.json'), 'r', encoding='utf-8') as f:
        cache = json.load(f)
    for key in ('market_news', 'japan_news'):
        cache[key] = [SimpleNamespace(**d) for d in cache.get(key, [])]
    for hm in cache.get('hot_markets', []):
        hm['news'] = [SimpleNamespace(**n) for n in hm.get('news', [])]
    return cache


# ── Dedup helpers ─────────────────────────────────────────────────────────────
def text_fingerprint(title, text):
    return (title + ' ' + text[:400]).lower().strip()

def is_duplicate(fp, seen_fps, threshold=None):
    thr = threshold if threshold is not None else SIMILARITY_THRESHOLD
    return any(SequenceMatcher(None, fp, s).ratio() >= thr for s in seen_fps)

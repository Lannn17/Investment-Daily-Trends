"""News pipeline: RSS fetch, HTML cleaning, dedup, scoring, translation, summarisation."""

import time
import datetime
import calendar
from types import SimpleNamespace

import feedparser
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from .config import (
    GEMINI_API_KEY, SCORE_MODEL_CHAIN, TRANSLATE_MODEL_CHAIN,
    SUMMARY_MODEL_CHAIN, INTRA_BATCH_THRESHOLD, TEST_MODE, FULLTEST_MODE,
)
from .state import text_fingerprint, is_duplicate
from .ai_client import score_entries, translate_titles, ai_summary

MIN_CONTENT_LENGTH = 80


# ── RSS fetch & HTML cleaning ─────────────────────────────────────────────────
def fetch_feed(url):
    try:
        ua = UserAgent()
        headers = {'User-Agent': ua.random.strip()}
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            return feedparser.parse(resp.content)
        print(f"  [rss] HTTP {resp.status_code} for {url}")
    except Exception as e:
        print(f"  [rss] Fetch failed ({url}): {e}")
    return None

def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup.find_all(['script', 'style', 'img', 'a', 'video', 'audio', 'iframe', 'input']):
        tag.decompose()
    return soup.get_text()


# ── News section processing pipeline ─────────────────────────────────────────
def process_news_section(urls, max_items, section_name, topic,
                         last_run_links, last_run_fps, current_run_fps, seen_links,
                         run_type='morning', morning_bench=None):
    """Fetch RSS, deduplicate, score, translate, summarise. Returns (entries, bench_items)."""
    candidates = []

    for url in urls:
        feed = fetch_feed(url)
        if not feed:
            continue
        for entry in feed.entries:
            if len(candidates) >= max_items * 8:
                break

            link = getattr(entry, 'link', '')
            if not link:
                continue
            if link in seen_links or link in last_run_links:
                continue
            if link in {c[0].link for c in candidates}:
                continue

            title = getattr(entry, 'title', None) or link[:80]

            # Skip articles older than 24 hours
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_ts = calendar.timegm(entry.published_parsed)
                now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                if now_ts - pub_ts > 86400:
                    continue

            # Extract article text
            try:
                article = entry.content[0].value
            except Exception:
                article = getattr(entry, 'description', title)
            cleaned = clean_html(article or title)
            if len(cleaned) < MIN_CONTENT_LENGTH:
                cleaned = title

            # Semantic dedup
            fp = text_fingerprint(title, cleaned)
            if is_duplicate(fp, last_run_fps) or is_duplicate(fp, current_run_fps):
                continue

            entry.title   = title
            entry.article = cleaned
            candidates.append((entry, fp, cleaned))

    # Evening re-pool: inject morning bench candidates
    if run_type == 'evening' and morning_bench:
        bench_list  = morning_bench.get(section_name, [])
        bench_links = {e.link for e, _, _ in candidates}
        for item in bench_list:
            if item['link'] in seen_links or item['link'] in last_run_links:
                continue
            if item['link'] in bench_links:
                continue
            fake = SimpleNamespace(title=item['title'], link=item['link'],
                                   article=item['article'], summary=None)
            candidates.append((fake, item['fp'], item['article']))
            bench_links.add(item['link'])

    if not candidates:
        return [], []

    # Score
    if GEMINI_API_KEY and SCORE_MODEL_CHAIN:
        scores = score_entries([e.title for e, _, _ in candidates], topic=topic)
        order  = sorted(range(len(candidates)), key=lambda i: -scores[i])
        time.sleep(3)
    else:
        order = list(range(len(candidates)))

    # Intra-batch dedup
    deduped, ibfps = [], []
    for i in order:
        _, fp, _ = candidates[i]
        if not is_duplicate(fp, ibfps, threshold=INTRA_BATCH_THRESHOLD):
            deduped.append(i)
            ibfps.append(fp)
    order = deduped

    # Save bench (morning only: ranked-out candidates)
    bench_items = []
    if run_type == 'morning' and len(order) > max_items:
        for i in order[max_items:]:
            e, fp_val, art = candidates[i]
            bench_items.append({
                'link': e.link, 'title': e.title,
                'article': art, 'fp': fp_val,
                'published': getattr(e, 'published', ''),
            })

    order = order[:max_items]
    if TEST_MODE and not FULLTEST_MODE:
        order = order[:2]

    # Translate titles
    if GEMINI_API_KEY and TRANSLATE_MODEL_CHAIN and order:
        raw_titles = [candidates[i][0].title for i in order]
        translated = translate_titles(raw_titles)
        if translated:
            for rank, i in enumerate(order):
                candidates[i][0].title = translated[rank]
        time.sleep(3)

    # Summarise
    entries = []
    for i in order:
        entry, fp, cleaned = candidates[i]
        if GEMINI_API_KEY and SUMMARY_MODEL_CHAIN:
            try:
                entry.summary = ai_summary(cleaned)
                if not entry.summary or not entry.summary.strip():
                    entry.summary = cleaned[:200]
            except Exception as e:
                entry.summary = cleaned[:200]
                print(f"  Summarisation failed for [{entry.title}]: {e}")
            time.sleep(3)
        else:
            entry.summary = None

        entries.append(entry)
        seen_links.add(entry.link)
        current_run_fps.append(fp)

    print(f"  [{section_name}] candidates: {len(candidates)} -> selected: {len(entries)}")
    return entries, bench_items

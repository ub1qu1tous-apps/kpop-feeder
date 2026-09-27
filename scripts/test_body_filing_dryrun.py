"""
Diagnostic only -- DRY RUN, writes nothing. Checks the planned
"read the whole article + file it under every group it names" pipeline
before we build it:

  1. Database stats: total stored articles, unique links, earliest dates.
  2. Samples stored articles, reads each one's text (googlenewsdecoder /
     Bing url= param -> trafilatura, newspaper4k fallback), and reports
     which OTHER groups each article would additionally be filed under
     by group name (with the surrounding text, so matches can be
     eyeballed for false positives). Also records whether a summary
     (page meta description) is available when the full text isn't.
  3. Simulates one scheduled run: pulls every group's current feeds and
     counts how many links aren't stored yet -- i.e. how many articles
     a normal 12-hour run would have to read.
  4. Estimates how long the one-time backfill of all stored articles takes.
"""

import os
import random
import re
import time
from collections import Counter, defaultdict
from urllib.parse import parse_qs, quote, urlparse

import feedparser
import requests
import trafilatura
from googlenewsdecoder import gnewsdecoder
from newspaper import Article

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

SAMPLE = {"google_news": 30, "bing_news": 20, "soompi": 10}
MIN_WORDS = 80
SOOMPI_FEED = "https://www.soompi.com/feed"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def rest_get(path, params, extra_headers=None):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{path}",
        headers={**HEADERS, **(extra_headers or {})},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp


def load_all_articles():
    rows, offset, page = [], 0, 1000
    while True:
        batch = rest_get(
            "articles",
            {"select": "id,group_key,source,title,url,published_at,fetched_at",
             "order": "id.asc", "limit": page, "offset": offset},
        ).json()
        rows.extend(batch)
        if len(batch) < page:
            return rows
        offset += page


# ---------------------------------------------------------------- matching

def group_name_aliases(group):
    """search_patterns minus member names -> just the group's own names."""
    members = {m.lower() for m in (group.get("members") or [])}
    aliases = {group["display_name"]: False}  # alias -> is_regex
    for p in group["search_patterns"]:
        plain = p.replace("\\b", "").replace("\\", "")
        if plain.lower() in members:
            continue
        aliases[p] = bool(group.get("is_regex")) and p != plain
    return aliases


def compile_body_matcher(group):
    """Group names only. Case-sensitive, but accepts the name as written,
    ALL CAPS, or Title Case -- so "TWICE"/"Twice" match but the everyday
    word "twice" doesn't; "IVE"/"Ive" match but not "ive"."""
    parts = []
    for alias, is_regex in group_name_aliases(group).items():
        if is_regex:
            parts.append(alias)
        else:
            for v in {alias, alias.upper(), alias.title()}:
                parts.append(rf"\b{re.escape(v)}\b")
    return re.compile("|".join(parts))


def snippet(text, m, width=60):
    s, e = max(0, m.start() - width), min(len(text), m.end() + width)
    return " ".join(text[s:e].split())


# ---------------------------------------------------------------- reading

def resolve(url, source):
    if source == "google_news":
        r = gnewsdecoder(url, interval=1)
        if r.get("status") or r.get("success"):
            return r["decoded_url"]
        raise RuntimeError(f"decode failed: {r.get('message')}")
    if source == "bing_news":
        qs = parse_qs(urlparse(url).query)
        if "url" in qs:
            return qs["url"][0]
    return url


def read_article(url, source):
    """Returns (text or None, summary or None, failure reason or None)."""
    try:
        real = resolve(url, source)
    except Exception as e:
        return None, None, f"resolve: {str(e)[:60]}"
    host = urlparse(real).netloc
    try:
        resp = requests.get(real, timeout=20, headers={"User-Agent": BROWSER_UA})
    except Exception as e:
        return None, None, f"fetch {type(e).__name__} ({host})"
    if resp.status_code != 200:
        return None, None, f"HTTP {resp.status_code} ({host})"
    html = resp.text

    summary = None
    try:
        meta = trafilatura.extract_metadata(html)
        summary = meta.description if meta else None
    except Exception:
        pass

    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    if len(text.split()) >= MIN_WORDS:
        return text, summary, None
    try:
        art = Article(real)
        art.download(input_html=html)
        art.parse()
        if len((art.text or "").split()) >= MIN_WORDS:
            return art.text, summary or art.meta_description or None, None
    except Exception:
        pass
    return None, summary, f"no text ({host})"


# ---------------------------------------------------------------- main

def main():
    random.seed(42)
    groups = rest_get("groups", {"select": "*"}).json()
    matchers = {g["key"]: compile_body_matcher(g) for g in groups}
    names = {g["key"]: g["display_name"] for g in groups}

    # 1. Database stats ---------------------------------------------------
    articles = load_all_articles()
    by_url = defaultdict(set)
    for a in articles:
        by_url[a["url"]].add(a["group_key"])
    print("=" * 70)
    print("1. DATABASE")
    print(f"Groups: {len(groups)}")
    print(f"Stored article rows: {len(articles)}  (unique links: {len(by_url)})")
    print("Per source: " + ", ".join(f"{k} {v}" for k, v in Counter(a['source'] for a in articles).items()))
    print("Per group:  " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(a['group_key'] for a in articles).items())))
    oldest_pub = min(articles, key=lambda a: a["published_at"])
    oldest_fetch = min(a["fetched_at"] for a in articles)
    print(f"Earliest article (publish date): {oldest_pub['published_at']}  [{oldest_pub['group_key']}] {oldest_pub['title'][:80]}")
    print(f"Earliest fetch by our system:    {oldest_fetch}")
    print("\nGroup-name terms used for text filing:")
    for g in groups:
        print(f"  {g['display_name']}: {list(group_name_aliases(g))}")

    # 2. Sample read + cross-filing --------------------------------------
    print("\n" + "=" * 70)
    print("2. SAMPLE READ + CROSS-FILING")
    firsts = {}
    for a in articles:
        firsts.setdefault(a["url"], a)
    sample = []
    for source, n in SAMPLE.items():
        pool = [a for a in firsts.values() if a["source"] == source]
        sample.extend(random.sample(pool, min(n, len(pool))))

    stats = defaultdict(Counter)
    fail = Counter()
    timings = []
    new_filings = Counter()
    google_decode_results = []

    for a in sample:
        src = a["source"]
        stats[src]["total"] += 1
        t0 = time.time()
        text, summary, reason = read_article(a["url"], src)
        timings.append(time.time() - t0)
        if src == "google_news":
            google_decode_results.append(not (reason or "").startswith("resolve"))

        if text:
            stats[src]["text"] += 1
        else:
            fail[reason] += 1
            if summary:
                stats[src]["summary_only"] += 1

        haystack = a["title"] + "\n" + (text or summary or "")
        already = by_url[a["url"]]
        extra = []
        for key, rx in matchers.items():
            if key in already:
                continue
            m = rx.search(haystack)
            if m:
                extra.append((key, m))
        status = "TEXT" if text else ("SUMMARY" if summary else f"FAIL {reason}")
        print(f"\n[{src}] {'/'.join(sorted(already))}: {a['title'][:80]}")
        print(f"    {status}  ({timings[-1]:.1f}s)")
        for key, m in extra:
            new_filings[key] += 1
            print(f"    + also file under {names[key]}: \"...{snippet(haystack, m)}...\"")

    print("\n" + "-" * 70)
    for src, s in stats.items():
        print(f"{src:12s} text {s['text']}/{s['total']}, summary-only {s['summary_only']}")
    print(f"Failure reasons: " + ", ".join(f"{k} x{v}" for k, v in fail.most_common()))
    print(f"Google link decoding: {sum(google_decode_results)}/{len(google_decode_results)} ok "
          f"(last 10: {sum(google_decode_results[-10:])}/10 -- a drop here would mean rate limiting)")
    avg = sum(timings) / len(timings)
    print(f"Avg time per article: {avg:.1f}s (max {max(timings):.1f}s)")
    print(f"Extra group filings found in {len(sample)} sampled articles: {sum(new_filings.values())} "
          f"-> " + ", ".join(f"{names[k]} {v}" for k, v in new_filings.most_common()))

    # 3. Simulated scheduled run ----------------------------------------
    print("\n" + "=" * 70)
    print("3. SIMULATED 12-HOUR RUN (feeds only, nothing read or saved)")
    stored_urls = set(by_url)
    seen, new_total, with_summary = set(), 0, 0
    soompi = feedparser.parse(SOOMPI_FEED).entries
    for e in soompi:
        link = e.get("link", "")
        if link and link not in stored_urls and link not in seen:
            seen.add(link)
            new_total += 1
            with_summary += bool(e.get("summary"))
    print(f"Soompi: {len(soompi)} in feed, {new_total} not stored yet")
    for g in groups:
        q = quote(f'"{g["display_name"]}" kpop')
        counts = {}
        for source, url in [
            ("google", f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"),
            ("bing", f"https://www.bing.com/news/search?q={q}&format=RSS"),
        ]:
            entries = feedparser.parse(url).entries[:20]
            n = 0
            for e in entries:
                link = e.get("link", "")
                if link and link not in stored_urls and link not in seen:
                    seen.add(link)
                    n += 1
                    with_summary += bool(e.get("summary"))
            counts[source] = n
        print(f"  {g['display_name']}: google {counts['google']} new, bing {counts['bing']} new")
    print(f"Links a run would read now: {len(seen)} (feed gives a summary for {with_summary})")
    print(f"Estimated extra time for this run: ~{len(seen) * avg / 60:.1f} min")
    print("(Some 'new' Google/Bing links may be the same story as a stored one "
          "and get dropped by the existing title de-dup before reading.)")

    # 4. Backfill estimate ----------------------------------------------
    print("\n" + "=" * 70)
    print("4. ONE-TIME BACKFILL ESTIMATE")
    print(f"{len(by_url)} unique links x {avg:.1f}s = ~{len(by_url) * avg / 60:.0f} min")


if __name__ == "__main__":
    main()

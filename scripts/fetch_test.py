"""
Proof-of-concept: for each tracked group, pull articles from:
  - Google News RSS (per-group search query)
  - Bing News RSS (per-group search query)
  - Soompi's direct feed (filtered by title match)
...merge them, drop near-duplicate stories (the same story often shows up
via more than one source/aggregator), and print the result.

This is NOT the final pipeline (no database writes yet) -- it just prints
what we get so we can see how well dedup works before building the real
thing.
"""

import difflib
import json
import re
from pathlib import Path
from urllib.parse import quote

import feedparser

GROUPS = json.loads((Path(__file__).parent / "groups.json").read_text())

SOOMPI_FEED = "https://www.soompi.com/feed"

# Priority order when two entries are judged duplicates: earlier wins.
# Soompi's own feed gives a clean direct link; Google News has better
# metadata/volume than Bing.
SOURCE_PRIORITY = {"soompi": 0, "google_news": 1, "bing_news": 2}

SUFFIX_RE = re.compile(r"\s-\s[^-]+$")  # strips trailing " - Publisher Name"
PUNCT_RE = re.compile(r"[^a-z0-9 ]")


def compile_matcher(group):
    if group.get("regex"):
        combined = "|".join(group["patterns"])
    else:
        combined = "|".join(re.escape(p) for p in group["patterns"])
    return re.compile(combined, re.IGNORECASE)


MATCHERS = {key: compile_matcher(g) for key, g in GROUPS.items()}


def normalize_title(title):
    title = SUFFIX_RE.sub("", title)
    title = title.lower()
    title = PUNCT_RE.sub("", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def fetch_feed(url):
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        return None, f"http status={parsed.get('status')}: {parsed.bozo_exception}"
    return parsed.entries, None


def dedupe(entries, threshold=0.85):
    """entries: list of dicts with 'title', 'link', 'source'. Keeps the
    first (highest-priority) copy of each near-duplicate story."""
    kept = []
    kept_norms = []
    dropped = 0
    for e in entries:
        norm = normalize_title(e["title"])
        is_dupe = any(
            difflib.SequenceMatcher(None, norm, kn).ratio() >= threshold
            for kn in kept_norms
        )
        if is_dupe:
            dropped += 1
            continue
        kept.append(e)
        kept_norms.append(norm)
    return kept, dropped


def main():
    print("=== Fetching Soompi (shared across all groups) ===")
    soompi_entries, err = fetch_feed(SOOMPI_FEED)
    if err:
        print(f"  FAILED: {err}")
        soompi_entries = []
    else:
        print(f"  {len(soompi_entries)} entries fetched")

    for group_key, group in GROUPS.items():
        print(f"\n########## {group['display_name']} ##########")
        combined = []

        for e in soompi_entries:
            if MATCHERS[group_key].search(e.get("title", "")):
                combined.append({"title": e.get("title", ""), "link": e.get("link", ""), "source": "soompi"})

        query = quote(f'"{group["display_name"]}" kpop')
        for agg_name, url in [
            ("google_news", f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"),
            ("bing_news", f"https://www.bing.com/news/search?q={query}&format=RSS"),
        ]:
            entries, err = fetch_feed(url)
            if err:
                print(f"  {agg_name} FAILED: {err}")
                continue
            for e in entries[:20]:
                combined.append({"title": e.get("title", ""), "link": e.get("link", ""), "source": agg_name})

        combined.sort(key=lambda e: SOURCE_PRIORITY.get(e["source"], 99))
        deduped, dropped = dedupe(combined)

        print(f"  {len(combined)} raw entries -> {len(deduped)} after dropping {dropped} near-duplicates")
        for e in deduped[:10]:
            print(f"  [{e['source']}] {e['title']}")


if __name__ == "__main__":
    main()

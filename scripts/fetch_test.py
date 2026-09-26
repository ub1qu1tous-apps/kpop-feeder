"""
Proof-of-concept: fetch a few K-pop news RSS feeds and see which articles
match which group, using simple substring/regex matching on the title.

This is NOT the final pipeline (no database writes yet) -- it just prints
what we get so we can refine the source list and matching rules before
building the real thing.
"""

import json
import re
from pathlib import Path
from urllib.parse import quote

import feedparser

# Confirmed working with feedparser's default request behavior.
# Dropped: allkpop and kpopmap (403 / malformed body under both default
# and browser user-agents -- looks like bot-protection, not a wrong URL;
# not worth fighting for a simple free RSS fetcher). koreaportal and
# whatthekpop: no working feed URL found yet.
SOURCES = {
    "soompi": "https://www.soompi.com/feed",
    "koreaboo": "https://www.koreaboo.com/feed/",
    "hellokpop": "https://www.hellokpop.com/feed/",
}

GROUPS = json.loads((Path(__file__).parent / "groups.json").read_text())


def compile_matcher(group):
    if group.get("regex"):
        combined = "|".join(group["patterns"])
    else:
        combined = "|".join(re.escape(p) for p in group["patterns"])
    return re.compile(combined, re.IGNORECASE)


MATCHERS = {key: compile_matcher(g) for key, g in GROUPS.items()}


def main():
    for source_name, url in SOURCES.items():
        print(f"\n=== {source_name} ({url}) ===")
        parsed = feedparser.parse(url)

        if parsed.bozo and not parsed.entries:
            print(f"  FAILED to fetch/parse (http status={parsed.get('status')}): {parsed.bozo_exception}")
            continue

        print(f"  {len(parsed.entries)} entries fetched")

        matched_count = 0
        for entry in parsed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            hits = [key for key, rx in MATCHERS.items() if rx.search(title)]
            if hits:
                matched_count += 1
                print(f"  [{', '.join(hits)}] {title}")
                print(f"      {link}")

        print(f"  -> {matched_count}/{len(parsed.entries)} entries matched a tracked group")


def test_news_aggregators():
    """
    Per-group search against news aggregators, instead of fetching a
    generic feed and filtering titles ourselves. The aggregator does the
    fetching from many outlets (including ones that block us directly,
    like allkpop) and hands back only matching results.
    """
    for group_key, group in GROUPS.items():
        query = quote(f'"{group["display_name"]}" kpop')
        google_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        bing_url = f"https://www.bing.com/news/search?q={query}&format=RSS"

        for agg_name, url in [("google_news", google_url), ("bing_news", bing_url)]:
            print(f"\n=== {agg_name}: {group_key} ({url}) ===")
            parsed = feedparser.parse(url)
            if parsed.bozo and not parsed.entries:
                print(f"  FAILED (http status={parsed.get('status')}): {parsed.bozo_exception}")
                continue
            print(f"  {len(parsed.entries)} entries")
            for entry in parsed.entries[:10]:
                print(f"  - {entry.get('title', '')}")
                print(f"      {entry.get('link', '')}")


if __name__ == "__main__":
    main()
    test_news_aggregators()

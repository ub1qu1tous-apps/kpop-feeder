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

import feedparser

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SOURCES = {
    "soompi": "https://www.soompi.com/feed",
    "koreaboo": "https://www.koreaboo.com/feed/",
    "kpopmap": "https://www.kpopmap.com/feed/",
    "hellokpop": "https://www.hellokpop.com/feed/",
    # dropped: koreaportal (/rss -> 404) and whatthekpop (domain doesn't
    # resolve -- bad guess). Re-add once real feed URLs are confirmed.
    "koreaportal_candidate_feed": "https://www.koreaportal.com/feed/",
    # allkpop's default guesses got a 403 (bot-protection) -- retrying
    # with a browser-like User-Agent.
    "allkpop_candidate_rss_xml": "https://www.allkpop.com/rss.xml",
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
        parsed = feedparser.parse(url, agent=USER_AGENT)

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


if __name__ == "__main__":
    main()

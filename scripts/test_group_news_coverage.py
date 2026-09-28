"""
Diagnostic only -- writes nothing. For one group: shows its stored
settings and article count, then what Google News / Bing News return for
the query the fetch job uses and for alternative spellings/aliases, and
how many of those results are on/after the oldest-article date.
"""

import os
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser
import requests

from fetch_and_store import fetch_oldest_date, is_too_old, parse_pubdate

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
MATCH = os.environ.get("GROUP_MATCH", "generation").lower()
EXTRA_QUERIES = [q.strip() for q in os.environ.get("EXTRA_QUERIES", "").split("|") if q.strip()]


def main():
    groups = requests.get(f"{SUPABASE_URL}/rest/v1/groups", headers=HEADERS, params={"select": "*"}, timeout=30).json()
    group = next(g for g in groups if MATCH in g["display_name"].lower() or MATCH in g["key"])
    print(f"key={group['key']!r} display_name={group['display_name']!r} is_regex={group['is_regex']}")
    print(f"members={group.get('members')}")
    print(f"search_patterns={group['search_patterns']}")

    rows = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles", headers=HEADERS,
        params={"select": "title,source,published_at,via_text", "group_key": f"eq.{group['key']}", "order": "published_at.desc"},
        timeout=30,
    ).json()
    print(f"\nStored articles: {len(rows)}")
    for r in rows[:15]:
        print(f"  {r['published_at'][:10]} [{r['source']}{', via text' if r['via_text'] else ''}] {r['title'][:90]}")

    oldest = fetch_oldest_date()
    print(f"\nOldest article date: {oldest.date() if oldest else 'not set'}")
    queries = [f'"{group["display_name"]}" kpop'] + EXTRA_QUERIES
    for q in queries:
        for source, url in [
            ("google", f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"),
            ("bing", f"https://www.bing.com/news/search?q={quote(q)}&format=RSS"),
        ]:
            entries = feedparser.parse(url).entries
            recent = [e for e in entries if not is_too_old(parse_pubdate(e).isoformat(), oldest)]
            marker = "  <- query the fetch job uses" if q == queries[0] else ""
            print(f"\n[{source}] {q!r}: {len(entries)} results, {len(recent)} on/after cutoff{marker}")
            for e in recent[:5]:
                print(f"    {parse_pubdate(e).date()} {e.get('title', '')[:95]}")


if __name__ == "__main__":
    main()

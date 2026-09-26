"""
Production fetch pipeline, run on a schedule (every 12h).

For each group in the `groups` table:
  - pull matching articles from Soompi's feed (shared fetch)
  - pull per-group results from Google News RSS and Bing News RSS
  - merge with already-stored articles from the last few days (so the
    same story doesn't get re-inserted under a different source/url on
    a later run), drop near-duplicates by title, and insert only the
    genuinely new ones.

Groups live in the database, not in a file here -- adding a new group
later is a plain INSERT into `groups`, no code change needed.
"""

import calendar
import difflib
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser
import requests

from translate_utils import maybe_translate_title

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

SOOMPI_FEED = "https://www.soompi.com/feed"

# "existing" (already in the DB) always wins a dedup tie, so a story we
# already stored never gets re-inserted just because a different source
# surfaced it this cycle.
SOURCE_PRIORITY = {"existing": -1, "soompi": 0, "google_news": 1, "bing_news": 2}

SUFFIX_RE = re.compile(r"\s-\s[^-]+$")  # strips trailing " - Publisher Name"
PUNCT_RE = re.compile(r"[^a-z0-9 ]")
DEDUP_WINDOW = timedelta(days=3)
DEDUP_THRESHOLD = 0.85


def normalize_title(title):
    title = SUFFIX_RE.sub("", title)
    title = title.lower()
    title = PUNCT_RE.sub("", title)
    return re.sub(r"\s+", " ", title).strip()


def compile_matcher(group):
    patterns = group["search_patterns"]
    if group.get("is_regex"):
        combined = "|".join(patterns)
    else:
        combined = "|".join(re.escape(p) for p in patterns)
    return re.compile(combined, re.IGNORECASE)


def fetch_groups():
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/groups", headers=HEADERS, params={"select": "*"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_existing_titles(group_key):
    cutoff = (datetime.now(timezone.utc) - DEDUP_WINDOW).isoformat()
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers=HEADERS,
        params={"select": "title", "group_key": f"eq.{group_key}", "fetched_at": f"gte.{cutoff}"},
        timeout=30,
    )
    resp.raise_for_status()
    return [row["title"] for row in resp.json()]


def fetch_feed(url):
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        return []
    return parsed.entries


def parse_pubdate(entry):
    if entry.get("published_parsed"):
        return datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def dedupe(entries, threshold=DEDUP_THRESHOLD):
    kept_norms = []
    kept = []
    for e in entries:
        norm = normalize_title(e["title"])
        if any(difflib.SequenceMatcher(None, norm, kn).ratio() >= threshold for kn in kept_norms):
            continue
        kept.append(e)
        kept_norms.append(norm)
    return kept


def insert_articles(rows):
    if not rows:
        return
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers={**HEADERS, "Prefer": "resolution=ignore-duplicates,return=minimal"},
        params={"on_conflict": "group_key,url"},
        json=rows,
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"  INSERT FAILED ({resp.status_code}): {resp.text[:500]}")
    resp.raise_for_status()


def main():
    groups = fetch_groups()

    only_key = os.environ.get("GROUP_KEY", "").strip()
    if only_key:
        groups = [g for g in groups if g["key"] == only_key]
        if not groups:
            raise SystemExit(f"No group found with key {only_key!r}")

    print(f"Loaded {len(groups)} group(s) from database")

    soompi_entries = fetch_feed(SOOMPI_FEED)
    print(f"Soompi: {len(soompi_entries)} entries fetched")

    for group in groups:
        key = group["key"]
        display_name = group["display_name"]
        matcher = compile_matcher(group)
        print(f"\n--- {display_name} ---")

        candidates = []
        for e in soompi_entries:
            if matcher.search(e.get("title", "")):
                candidates.append(
                    {
                        "title": maybe_translate_title(e.get("title", "")),
                        "url": e.get("link", ""),
                        "source": "soompi",
                        "published_at": parse_pubdate(e).isoformat(),
                    }
                )

        query = quote(f'"{display_name}" kpop')
        for source, url in [
            ("google_news", f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"),
            ("bing_news", f"https://www.bing.com/news/search?q={query}&format=RSS"),
        ]:
            for e in fetch_feed(url)[:20]:
                candidates.append(
                    {
                        "title": maybe_translate_title(e.get("title", "")),
                        "url": e.get("link", ""),
                        "source": source,
                        "published_at": parse_pubdate(e).isoformat(),
                    }
                )

        existing_titles = fetch_existing_titles(key)
        pool = [{"title": t, "source": "existing"} for t in existing_titles] + candidates
        pool.sort(key=lambda e: SOURCE_PRIORITY.get(e["source"], 99))
        deduped = dedupe(pool)

        new_rows = [
            {
                "group_key": key,
                "source": e["source"],
                "title": e["title"],
                "url": e["url"],
                "published_at": e["published_at"],
            }
            for e in deduped
            if e["source"] != "existing"
        ]

        insert_articles(new_rows)
        print(
            f"  {len(candidates)} candidates, {len(existing_titles)} existing titles considered "
            f"-> {len(new_rows)} new rows inserted"
        )


if __name__ == "__main__":
    main()

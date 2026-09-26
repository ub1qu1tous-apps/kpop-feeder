"""
One-off utility: fill in the `publisher` column for articles stored
before that field existed. The publisher name is still sitting in the
stored title text (e.g. "... - Forbes"), so this re-parses it rather
than re-fetching anything. Safe to re-run -- only touches rows where
publisher is currently null.
"""

import os
import re

import requests

PUBLISHER_RE = re.compile(r"\s-\s([^-]+)$")

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def extract_publisher(title):
    m = PUBLISHER_RE.search(title)
    return m.group(1).strip() if m else None


def fetch_articles_missing_publisher():
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers=HEADERS,
        params={"select": "id,title,source", "publisher": "is.null", "order": "id.asc", "limit": 5000},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_publisher(article_id, publisher):
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers={**HEADERS, "Prefer": "return=minimal"},
        params={"id": f"eq.{article_id}"},
        json={"publisher": publisher},
        timeout=30,
    )
    resp.raise_for_status()


def main():
    articles = fetch_articles_missing_publisher()
    print(f"Found {len(articles)} articles with no publisher set")

    updated = 0
    for a in articles:
        if a["source"] == "soompi":
            publisher = "Soompi"
        else:
            publisher = extract_publisher(a["title"])

        if publisher:
            update_publisher(a["id"], publisher)
            updated += 1
            print(f"  #{a['id']} [{a['source']}]: {publisher!r}")

    print(f"Done. {updated} article(s) backfilled.")


if __name__ == "__main__":
    main()

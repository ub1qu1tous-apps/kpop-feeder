"""
One-off utility: translate any already-stored non-English article
titles to English. Safe to re-run -- titles already in English (or
already translated) are left untouched. Not part of the scheduled
pipeline; run manually via its own workflow_dispatch when needed.
"""

import os

import requests

from translate_utils import maybe_translate_title

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def fetch_all_articles():
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers=HEADERS,
        params={"select": "id,title", "order": "id.asc", "limit": 5000},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_title(article_id, new_title):
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers={**HEADERS, "Prefer": "return=minimal"},
        params={"id": f"eq.{article_id}"},
        json={"title": new_title},
        timeout=30,
    )
    resp.raise_for_status()


def main():
    articles = fetch_all_articles()
    print(f"Checking {len(articles)} stored articles for non-English titles")

    updated = 0
    for a in articles:
        translated = maybe_translate_title(a["title"])
        if translated != a["title"]:
            update_title(a["id"], translated)
            updated += 1
            print(f"  #{a['id']}: {a['title']!r} -> {translated!r}")

    print(f"Done. {updated} title(s) translated.")


if __name__ == "__main__":
    main()

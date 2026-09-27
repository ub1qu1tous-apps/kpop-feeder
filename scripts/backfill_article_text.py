"""
One-time pass over every article already stored (safe to re-run -- it
skips links already read and filings that already exist):

  1. fills in link_key on stored articles
  2. reads the full text of every stored link not read yet
  3. files each article under every other group whose name appears in
     its text (or title/summary), skipping near-duplicate titles

Re-running this after adding a new group also files older stored
articles that mention it.
"""

import difflib
import os
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

import article_text
from fetch_and_store import DEDUP_THRESHOLD, normalize_title

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def get_all(path, select, order):
    rows, offset, page = [], 0, 1000
    while True:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS,
            params={"select": select, "order": order, "limit": page, "offset": offset}, timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < page:
            return rows
        offset += page


def set_link_key(article):
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers={**HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"},
        params={"id": f"eq.{article['id']}"},
        json={"link_key": article["link_key"]},
        timeout=30,
    )
    resp.raise_for_status()


def main():
    groups = requests.get(f"{SUPABASE_URL}/rest/v1/groups", headers=HEADERS,
                          params={"select": "*"}, timeout=30).json()
    articles = get_all("articles", "id,group_key,source,title,url,publisher,published_at,link_key", "id.asc")
    print(f"{len(articles)} stored articles, {len(groups)} groups")

    # 1. link keys ---------------------------------------------------------
    missing = [a for a in articles if not a.get("link_key")]
    for a in missing:
        a["link_key"] = article_text.link_key(a["source"], a["url"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(set_link_key, missing))
    print(f"Step 1: set link_key on {len(missing)} articles")

    # 2. read text ---------------------------------------------------------
    known = article_text.load_known_link_keys(SUPABASE_URL, HEADERS)
    first_by_key = {}
    for a in articles:
        first_by_key.setdefault(a["link_key"], a)
    to_read = [
        {"source": a["source"], "url": a["url"]}
        for k, a in first_by_key.items() if k not in known
    ]
    print(f"Step 2: reading {len(to_read)} links not read yet...")
    results = article_text.read_many(to_read)
    article_text.save_texts(SUPABASE_URL, HEADERS, [row for _, row in results])
    status = Counter(row["status"] for _, row in results)
    print(
        f"  read {len(results)}/{len(to_read)}: text {status['text']}, "
        f"summary only {status['summary']}, title only {status['failed']}, "
        f"{len(to_read) - len(results)} couldn't be resolved (re-run later to retry)"
    )

    # 3. file by group name ------------------------------------------------
    texts = {t["link_key"]: t for t in get_all("article_texts", "link_key,body,summary", "link_key.asc")}
    groups_with_key = defaultdict(set)
    titles_by_group = defaultdict(list)
    for a in articles:
        groups_with_key[a["link_key"]].add(a["group_key"])
        titles_by_group[a["group_key"]].append(normalize_title(a["title"]))

    matchers = {g["key"]: article_text.compile_name_matcher(g) for g in groups}
    new_rows = []
    for key, a in first_by_key.items():
        haystack = article_text.searchable_text(a["title"], texts.get(key))
        for gkey, mentions in matchers.items():
            if gkey in groups_with_key[key] or not mentions(haystack):
                continue
            norm = normalize_title(a["title"])
            if any(difflib.SequenceMatcher(None, norm, t).ratio() >= DEDUP_THRESHOLD
                   for t in titles_by_group[gkey]):
                continue
            titles_by_group[gkey].append(norm)
            groups_with_key[key].add(gkey)
            new_rows.append({
                "group_key": gkey, "source": a["source"], "title": a["title"], "url": a["url"],
                "publisher": a["publisher"], "published_at": a["published_at"],
                "link_key": key, "via_text": not mentions(a["title"]),
            })

    for i in range(0, len(new_rows), 200):
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/articles",
            headers={**HEADERS, "Content-Type": "application/json",
                     "Prefer": "resolution=ignore-duplicates,return=minimal"},
            params={"on_conflict": "group_key,url"},
            json=new_rows[i:i + 200],
            timeout=60,
        )
        if resp.status_code >= 300:
            print(f"  INSERT FAILED ({resp.status_code}): {resp.text[:300]}")
        resp.raise_for_status()

    names = {g["key"]: g["display_name"] for g in groups}
    per_group = Counter(r["group_key"] for r in new_rows)
    print(f"Step 3: filed {len(new_rows)} extra articles by group name: "
          + (", ".join(f"{names[k]} +{v}" for k, v in per_group.most_common()) or "none"))


if __name__ == "__main__":
    main()

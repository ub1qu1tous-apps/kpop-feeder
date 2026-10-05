"""
Production fetch pipeline, run on a schedule (every 12h).

For each group in the `groups` table:
  - pull matching articles from Soompi's feed (shared fetch)
  - pull per-group results from Google News RSS and Bing News RSS
  - merge with already-stored articles from the last few days (so the
    same story doesn't get re-inserted under a different source/url on
    a later run), drop near-duplicates by title, and insert only the
    genuinely new ones.

Then, for every link not read before (article_texts is the "already
read" list), read the full article text, save it for keyword search,
and also file the article under every group whose name appears in it.
Only new links are read, so scheduled runs and refreshes stay quick.

Groups live in the database, not in a file here -- adding a new group
later is a plain INSERT into `groups`, no code change needed.
"""

import calendar
import difflib
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser
import requests

import article_text
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
PUBLISHER_RE = re.compile(r"\s-\s([^-]+)$")  # captures the same suffix
PUNCT_RE = re.compile(r"[^a-z0-9 ]")
DEDUP_WINDOW = timedelta(days=3)
DEDUP_THRESHOLD = 0.85


def normalize_title(title):
    title = SUFFIX_RE.sub("", title)
    title = title.lower()
    title = PUNCT_RE.sub("", title)
    return re.sub(r"\s+", " ", title).strip()


def extract_publisher(raw_title):
    """Pulls the "- Publisher Name" suffix Google/Bing News append to
    titles. Run on the raw (pre-translation) title since translating the
    whole string can mangle a non-English publisher name."""
    m = PUBLISHER_RE.search(raw_title)
    return m.group(1).strip() if m else None


def compile_matcher(group):
    """Literal (non-regex) patterns are always word-bounded, so a short
    name like "Han" can't match as a mid-word substring (e.g. inside
    "Hands"). Raw regex patterns (is_regex=true) are trusted to bound
    themselves -- that's the whole point of using regex for them."""
    patterns = group["search_patterns"]
    if group.get("is_regex"):
        combined = "|".join(patterns)
    else:
        combined = "|".join(article_text.literal_pattern(p) for p in patterns)
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


FEED_TIMEOUT = 20  # seconds


def fetch_feed(url):
    """Fetch and parse one RSS feed.

    Deliberately not feedparser.parse(url) -- that has no timeout of its
    own, and a feed server that hangs instead of erroring blocks forever
    (this stalled a whole run for 15 minutes on 2026-10-05 until it was
    cancelled). Fetching the bytes ourselves bounds it to FEED_TIMEOUT;
    a slow or failing source is logged and skipped rather than taking
    the rest of the run down with it.
    """
    try:
        resp = requests.get(url, timeout=FEED_TIMEOUT, headers={"User-Agent": article_text.BROWSER_UA})
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  (feed fetch failed, skipping -- {url}: {exc})")
        return []
    parsed = feedparser.parse(resp.content)
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


def report_fetch_status(ok, error=None):
    """Only meaningful for the full scheduled run (all groups) -- a
    single-group manual refresh doesn't touch this, so the timestamp
    reflects "when did the last full sweep last succeed/fail"."""
    try:
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/fetch_status",
            headers={**HEADERS, "Prefer": "return=minimal"},
            params={"id": "eq.1"},
            json={
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_run_ok": ok,
                "last_error": (str(error)[:500] if error else None),
            },
            timeout=30,
        )
    except Exception as report_err:
        print(f"  (failed to report fetch_status: {report_err})")


def fetch_oldest_date():
    """Admin setting (app_settings table): articles published before this
    date are never stored. None if the setting isn't set up yet."""
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/app_settings",
            headers=HEADERS,
            params={"select": "oldest_article_date", "id": "eq.1"},
            timeout=30,
        )
        if resp.status_code == 200 and resp.json():
            day = datetime.fromisoformat(resp.json()[0]["oldest_article_date"])
            return day.replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"  (couldn't load oldest_article_date: {e})")
    return None


def is_too_old(published_at, oldest):
    return oldest is not None and datetime.fromisoformat(published_at) < oldest


def make_item(source, entry):
    """One feed entry, before translation/filing."""
    url = entry.get("link", "")
    return {
        "source": source,
        "url": url,
        "raw_title": entry.get("title", ""),
        "published_at": parse_pubdate(entry).isoformat(),
        "feed_summary": entry.get("summary"),
        "link_key": article_text.link_key(source, url),
    }


_translated = {}


def to_candidate(item, via_text=False):
    raw = item["raw_title"]
    if raw not in _translated:
        _translated[raw] = maybe_translate_title(raw)
    return {
        "title": _translated[raw],
        "url": item["url"],
        "source": item["source"],
        "publisher": "Soompi" if item["source"] == "soompi" else extract_publisher(raw),
        "published_at": item["published_at"],
        "link_key": item["link_key"],
        "via_text": via_text,
    }


def file_by_text(items, all_groups, candidates_by_group, known_keys):
    """Reads every link not read before, saves its text, and adds it as a
    candidate for each group whose name appears in it."""
    to_read, seen = [], set()
    for item in items:
        k = item["link_key"]
        if k and k not in known_keys and k not in seen:
            seen.add(k)
            to_read.append(item)
    if not to_read:
        print("\nArticle text: nothing new to read")
        return

    results = article_text.read_many(to_read)
    article_text.save_texts(SUPABASE_URL, HEADERS, [row for _, row in results])
    status = Counter(row["status"] for _, row in results)
    print(
        f"\nArticle text: read {len(results)}/{len(to_read)} new links "
        f"(text {status['text']}, summary only {status['summary']}, title only {status['failed']}; "
        f"{len(to_read) - len(results)} to retry next run)"
    )

    name_matchers = {g["key"]: article_text.compile_name_matcher(g) for g in all_groups}
    for item, row in results:
        haystack = article_text.searchable_text(item["raw_title"], row)
        for key, mentions in name_matchers.items():
            if mentions(haystack):
                # via_text = only the article body names the group, not the title
                candidates_by_group[key].append(to_candidate(item, via_text=not mentions(item["raw_title"])))


def main():
    only_key = os.environ.get("GROUP_KEY", "").strip()
    is_full_run = not only_key

    all_groups = fetch_groups()
    groups = all_groups

    if only_key:
        groups = [g for g in all_groups if g["key"] == only_key]
        if not groups:
            raise SystemExit(f"No group found with key {only_key!r}")

    print(f"Loaded {len(groups)} group(s) from database")

    text_on = article_text.text_tables_ready(SUPABASE_URL, HEADERS)
    if not text_on:
        print("NOTE: article text tables not set up yet (run supabase/006_article_texts.sql) -- titles only")

    oldest = fetch_oldest_date()
    print(f"Oldest article date: {oldest.date() if oldest else 'not set'}")
    too_old = 0

    soompi_items = []
    for e in fetch_feed(SOOMPI_FEED):
        item = make_item("soompi", e)
        if is_too_old(item["published_at"], oldest):
            too_old += 1
        else:
            soompi_items.append(item)
    print(f"Soompi: {len(soompi_items)} entries fetched")
    all_items = list(soompi_items)  # everything seen this run, for text reading

    # Direct filing, same as before: Soompi by title match, Google/Bing by
    # the group's own news search.
    candidates_by_group = defaultdict(list)
    for group in groups:
        key = group["key"]
        matcher = compile_matcher(group)
        for item in soompi_items:
            if matcher.search(item["raw_title"]):
                candidates_by_group[key].append(to_candidate(item))

        name = group["display_name"]
        google_query = quote(f'"{name}" kpop')
        # Bing News returns nothing for quoted names containing an
        # apostrophe ("Girls' Generation"), but finds them without it.
        bing_query = quote(f'"{article_text.APOSTROPHE_RE.sub("", name)}" kpop')
        for source, url in [
            ("google_news", f"https://news.google.com/rss/search?q={google_query}&hl=en-US&gl=US&ceid=US:en"),
            ("bing_news", f"https://www.bing.com/news/search?q={bing_query}&format=RSS"),
        ]:
            for e in fetch_feed(url)[:20]:
                item = make_item(source, e)
                if is_too_old(item["published_at"], oldest):
                    too_old += 1
                    continue
                all_items.append(item)
                candidates_by_group[key].append(to_candidate(item))

    if too_old:
        print(f"Skipped {too_old} feed entries published before the oldest article date")

    # Filing by article text: any group named anywhere in a newly read
    # article gets it too -- including groups other than the one refreshed.
    if text_on:
        known_keys = article_text.load_known_link_keys(SUPABASE_URL, HEADERS)
        file_by_text(all_items, all_groups, candidates_by_group, known_keys)

    names = {g["key"]: g["display_name"] for g in all_groups}
    for key, candidates in candidates_by_group.items():
        print(f"\n--- {names.get(key, key)} ---")
        existing_titles = fetch_existing_titles(key)
        pool = [{"title": t, "source": "existing"} for t in existing_titles] + candidates
        pool.sort(key=lambda e: SOURCE_PRIORITY.get(e["source"], 99))
        deduped = dedupe(pool)

        new_rows = []
        for e in deduped:
            if e["source"] == "existing":
                continue
            row = {
                "group_key": key,
                "source": e["source"],
                "title": e["title"],
                "url": e["url"],
                "publisher": e.get("publisher"),
                "published_at": e["published_at"],
            }
            if text_on:
                row["link_key"] = e["link_key"]
                row["via_text"] = e["via_text"]
            new_rows.append(row)

        insert_articles(new_rows)
        via_text = sum(1 for r in new_rows if r.get("via_text"))
        print(
            f"  {len(candidates)} candidates, {len(existing_titles)} existing titles considered "
            f"-> {len(new_rows)} new rows inserted ({via_text} because the article text names the group)"
        )

    if is_full_run:
        report_fetch_status(ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if not os.environ.get("GROUP_KEY", "").strip():
            report_fetch_status(ok=False, error=exc)
        raise

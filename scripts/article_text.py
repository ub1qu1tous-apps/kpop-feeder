"""
Shared helpers for reading an article's full text and filing it under
every group whose NAME appears in it (member names are deliberately not
used here -- in full articles, names like "Winter" or "Han" show up as
ordinary words far too often).

Used by fetch_and_store.py (new articles each run) and
backfill_article_text.py (one-time pass over everything already stored).
"""

import html
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import requests
import trafilatura
from googlenewsdecoder import gnewsdecoder

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MIN_WORDS = 80  # less than this is nav/boilerplate, not an article
MAX_BODY_CHARS = 50000
MAX_SUMMARY_CHARS = 1000
READ_WORKERS = 8

# Group names that are also everyday English words. In article text these
# only count when capitalised ("TWICE"/"Twice", never "won twice");
# every other group name matches in any case ("aespa", "Aespa", "AESPA").
COMMON_WORD_NAMES = {"twice", "ive", "seventeen", "treasure", "winner"}

TAG_RE = re.compile(r"<[^>]+>")
APOSTROPHE_RE = re.compile("['\u2019\u2018]")
ANY_APOSTROPHE = "['\u2019\u2018]"

# Google News decoding goes one at a time so we don't get rate limited;
# publisher pages are fetched in parallel.
_google_lock = threading.Lock()


# ---------------------------------------------------------------- links

def link_key(source, url):
    """Stable identity for an article link. Bing adds a fresh tracking id
    to every feed link, so use the real publisher URL it carries; Google
    News article links are stable once the query string is dropped."""
    if source == "bing_news":
        qs = parse_qs(urlparse(url).query)
        if "url" in qs:
            return qs["url"][0]
    if source == "google_news":
        return url.split("?", 1)[0]
    return url


def resolve(source, url):
    """Returns the publisher URL, or None if it couldn't be worked out
    (e.g. Google rate limiting) -- the caller then retries next run."""
    if source == "google_news":
        with _google_lock:
            try:
                r = gnewsdecoder(url, interval=1)
            except Exception:
                return None
        if r.get("status") or r.get("success"):
            return r["decoded_url"]
        return None
    return link_key(source, url)


# ---------------------------------------------------------------- reading

def clean_summary(text):
    if not text:
        return None
    text = " ".join(html.unescape(TAG_RE.sub(" ", text)).split())
    return text[:MAX_SUMMARY_CHARS] or None


def read_article(source, url, feed_summary=None):
    """Returns an article_texts row, or None if the link couldn't be
    resolved (not stored, so it's retried next run)."""
    key = link_key(source, url)
    real = resolve(source, url)
    if not real:
        return None
    # Google's own feed "summary" is just the title again -- not useful.
    fallback_summary = clean_summary(feed_summary) if source != "google_news" else None
    row = {"link_key": key, "resolved_url": real, "status": "failed", "body": None, "summary": fallback_summary}

    try:
        resp = requests.get(real, timeout=15, headers={"User-Agent": BROWSER_UA})
        if resp.status_code != 200:
            return _finish(row)
        page = resp.text
    except Exception:
        return _finish(row)

    try:
        meta = trafilatura.extract_metadata(page)
        if meta and meta.description:
            row["summary"] = clean_summary(meta.description)
    except Exception:
        pass
    try:
        body = trafilatura.extract(page, include_comments=False, include_tables=False) or ""
    except Exception:
        body = ""
    if len(body.split()) >= MIN_WORDS:
        row["body"] = body[:MAX_BODY_CHARS]
        row["status"] = "text"
    return _finish(row)


def _finish(row):
    if row["status"] != "text" and row["summary"]:
        row["status"] = "summary"
    return row


def read_many(items):
    """items: dicts with source, url, feed_summary. Returns a list of
    (item, row) for every link that resolved."""
    def work(item):
        return item, read_article(item["source"], item["url"], item.get("feed_summary"))

    with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
        return [(item, row) for item, row in pool.map(work, items) if row]


def searchable_text(title, row):
    """Title plus whatever we got for the article: full text if we have
    it, else the summary."""
    extra = (row or {}).get("body") or (row or {}).get("summary") or ""
    return f"{title}\n{extra}"


# ---------------------------------------------------------------- matching

def literal_pattern(term):
    """Word-bounded regex for a plain search term. Any apostrophe style
    matches any other: headlines often write "Girls\u2019 Generation"
    (curly) where the stored name has a straight "'"."""
    escaped = APOSTROPHE_RE.sub(lambda _: ANY_APOSTROPHE, re.escape(term))
    return rf"\b{escaped}\b"


def group_name_aliases(group):
    """search_patterns minus member names -> just the group's own names.
    Returns {alias: is_regex}."""
    members = {m.lower() for m in (group.get("members") or [])}
    aliases = {group["display_name"]: False}
    for p in group.get("search_patterns") or []:
        plain = p.replace("\\b", "").replace("\\", "")
        if plain.lower() in members:
            continue
        aliases[p] = bool(group.get("is_regex")) and p != plain
    return aliases


def compile_name_matcher(group):
    """Returns fn(text) -> bool: does the text name this group?"""
    any_case, capitalised = [], []
    for alias, is_regex in group_name_aliases(group).items():
        plain = alias.replace("\\b", "").replace("\\", "")
        if plain.lower() in COMMON_WORD_NAMES:
            if is_regex:
                capitalised.append(alias)
            else:
                capitalised.extend(literal_pattern(v) for v in {alias, alias.upper(), alias.title()})
        else:
            any_case.append(alias if is_regex else literal_pattern(alias))

    rx_any = re.compile("|".join(any_case), re.IGNORECASE) if any_case else None
    rx_cap = re.compile("|".join(capitalised)) if capitalised else None
    return lambda text: bool((rx_any and rx_any.search(text)) or (rx_cap and rx_cap.search(text)))


# ---------------------------------------------------------------- storage

def load_known_link_keys(supabase_url, headers):
    keys, offset, page = set(), 0, 1000
    while True:
        resp = requests.get(
            f"{supabase_url}/rest/v1/article_texts",
            headers=headers,
            params={"select": "link_key", "order": "link_key.asc", "limit": page, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        keys.update(r["link_key"] for r in batch)
        if len(batch) < page:
            return keys
        offset += page


def save_texts(supabase_url, headers, rows, chunk=50):
    for i in range(0, len(rows), chunk):
        resp = requests.post(
            f"{supabase_url}/rest/v1/article_texts",
            headers={**headers, "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            params={"on_conflict": "link_key"},
            json=rows[i:i + chunk],
            timeout=60,
        )
        if resp.status_code >= 300:
            print(f"  SAVE TEXT FAILED ({resp.status_code}): {resp.text[:300]}")
        resp.raise_for_status()


def text_tables_ready(supabase_url, headers):
    """False until supabase/006_article_texts.sql has been run -- lets the
    fetch job keep working the old way instead of crashing."""
    for path, col in [("article_texts", "link_key"), ("articles", "link_key")]:
        resp = requests.get(
            f"{supabase_url}/rest/v1/{path}", headers=headers,
            params={"select": col, "limit": 1}, timeout=30,
        )
        if resp.status_code != 200:
            return False
    return True

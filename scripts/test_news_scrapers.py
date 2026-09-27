"""
Diagnostic only -- not part of the pipeline. Compares free article-text
extractors on one live article from Google News RSS and one from Bing
News RSS (same feed URLs fetch_and_store.py uses), so it needs no
Supabase access.

For each feed: take the newest entry, resolve the feed's redirect link
to the publisher URL, fetch the page once, then run every extractor and
report how many words each got out, the most frequent words, and a
preview.

Extractors tested (all free, no API key):
  - trafilatura   (pip, Apache-2.0)
  - newspaper4k   (pip, MIT; maintained fork of newspaper3k)
  - Jina Reader   (hosted, https://r.jina.ai/<url>, free tier)
"""

import os
import re
import sys
from collections import Counter
from urllib.parse import parse_qs, quote_plus, urlparse

import feedparser
import requests
import trafilatura
from googlenewsdecoder import gnewsdecoder
from newspaper import Article

QUERY = os.environ.get("QUERY") or "aespa"
MAX_TRIES = 3  # fall through to the next entry if a publisher blocks us

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because
been before being below between both but by can could did do does doing down
during each few for from further had has have having he her here hers herself
him himself his how i if in into is it its itself just me more most my myself
no nor not now of off on once only or other our ours ourselves out over own
said same she should so some such than that the their theirs them themselves
then there these they this those through to too under until up very was we
were what when where which while who whom why will with would you your yours
yourself yourselves s t one new us like get got via per
""".split())


def resolve_google(link):
    result = gnewsdecoder(link, interval=1)
    # 0.2.x returns "success"; older releases used "status".
    if result.get("success") or result.get("status"):
        return result["decoded_url"]
    raise RuntimeError(f"googlenewsdecoder failed: {result.get('message')}")


def resolve_bing(link):
    # Bing RSS links are bing.com/news/apiclick.aspx?...&url=<publisher url>
    qs = parse_qs(urlparse(link).query)
    if "url" in qs:
        return qs["url"][0]
    resp = requests.get(link, timeout=20, headers={"User-Agent": BROWSER_UA})
    return resp.url


def fetch_html(url):
    resp = requests.get(url, timeout=20, headers={"User-Agent": BROWSER_UA})
    resp.raise_for_status()
    return resp.text


def run_trafilatura(url, html):
    return trafilatura.extract(html, include_comments=False, include_tables=False) or ""


def run_newspaper(url, html):
    art = Article(url)
    art.download(input_html=html)
    art.parse()
    return art.text or ""


def run_jina(url, html):
    resp = requests.get(f"https://r.jina.ai/{url}", timeout=45, headers={"Accept": "text/plain"})
    resp.raise_for_status()
    # Jina prepends "Title:/URL Source:/Markdown Content:" headers; keep the body.
    body = resp.text.split("Markdown Content:", 1)[-1]
    # Strip markdown links/images so word counts are comparable.
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)
    body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)
    return body.strip()


EXTRACTORS = [
    ("trafilatura", run_trafilatura),
    ("newspaper4k", run_newspaper),
    ("jina-reader", run_jina),
]


def words_of(text):
    return re.findall(r"[A-Za-z][A-Za-z'\-]+", text)


def top_words(words, n=15):
    counts = Counter(w.lower() for w in words if w.lower() not in STOPWORDS and len(w) > 2)
    return ", ".join(f"{w}({c})" for w, c in counts.most_common(n))


def test_feed(name, feed_url, resolver):
    print("=" * 78)
    print(f"{name.upper()}  --  {feed_url}")
    print("=" * 78)
    feed = feedparser.parse(feed_url)
    if not feed.entries:
        print(f"  Feed returned no entries (bozo={feed.get('bozo_exception')})\n")
        return False

    for entry in feed.entries[:MAX_TRIES]:
        print(f"  Title:    {entry.title}")
        print(f"  Feed link: {entry.link[:120]}")
        try:
            url = resolver(entry.link)
            print(f"  Resolved: {url}")
            html = fetch_html(url)
            print(f"  Fetched {len(html):,} chars of HTML")
        except Exception as e:
            print(f"  SKIP -- could not resolve/fetch: {e}\n")
            continue

        for ext_name, fn in EXTRACTORS:
            print(f"\n  --- {ext_name} ---")
            try:
                text = fn(url, html)
            except Exception as e:
                print(f"  FAILED: {type(e).__name__}: {e}")
                continue
            words = words_of(text)
            if not words:
                print("  FAILED: no text extracted")
                continue
            print(f"  Words: {len(words):,}   Chars: {len(text):,}")
            print(f"  Top words: {top_words(words)}")
            preview = " ".join(text.split())[:500]
            print(f"  Preview: {preview}")
        print()
        return True

    print(f"  All {MAX_TRIES} entries failed to fetch.\n")
    return False


def main():
    q = quote_plus(QUERY)
    ok_google = test_feed(
        "Google News",
        f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
        resolve_google,
    )
    ok_bing = test_feed(
        "Bing News",
        f"https://www.bing.com/news/search?q={q}&format=RSS",
        resolve_bing,
    )
    print(f"Summary: google_news={'OK' if ok_google else 'FAILED'}  bing_news={'OK' if ok_bing else 'FAILED'}")
    sys.exit(0 if (ok_google and ok_bing) else 1)


if __name__ == "__main__":
    main()

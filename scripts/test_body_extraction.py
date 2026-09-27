"""
Diagnostic only -- not part of the pipeline. Runs the method from the
extractor evaluation on a realistic sample of *stored* articles:
  - Google News links -> googlenewsdecoder -> publisher URL
  - Bing News links   -> publisher URL from the url= query param
  - Soompi links      -> already direct
then fetches each page and extracts body text with trafilatura
(newspaper4k as fallback). Reports per-source success rates, failure
reasons, and -- the actual goal -- how many articles mention a member
in the body but not in the title.
"""

import os
import re
import time
from collections import Counter, defaultdict
from urllib.parse import parse_qs, urlparse

import requests
import trafilatura
from googlenewsdecoder import gnewsdecoder
from newspaper import Article

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

PER_SOURCE = int(os.environ.get("PER_SOURCE", "8"))
MIN_WORDS = 80  # below this we treat the extraction as a failure (nav/boilerplate only)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def rest_get(path, params):
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def sample_articles():
    # Spread across groups: pull a wider window per source, then take at
    # most one article per group until PER_SOURCE is reached.
    out = []
    for source in ["google_news", "bing_news", "soompi"]:
        rows = rest_get(
            "articles",
            {"select": "id,group_key,title,url,source", "source": f"eq.{source}",
             "order": "published_at.desc", "limit": 200},
        )
        seen, picked = set(), []
        for r in rows:
            if r["group_key"] not in seen:
                picked.append(r)
                seen.add(r["group_key"])
            if len(picked) == PER_SOURCE:
                break
        out.extend(picked)
    return out


def load_members():
    return {g["key"]: g.get("members") or [] for g in rest_get("groups", {"select": "key,members"})}


def resolve(article):
    link = article["url"]
    if article["source"] == "google_news":
        result = gnewsdecoder(link, interval=1)
        if result.get("success") or result.get("status"):
            return result["decoded_url"]
        raise RuntimeError(f"decode failed: {result.get('message')}")
    if article["source"] == "bing_news":
        qs = parse_qs(urlparse(link).query)
        if "url" in qs:
            return qs["url"][0]
    return link


def extract(url, html):
    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    if len(text.split()) >= MIN_WORDS:
        return text, "trafilatura"
    try:
        art = Article(url)
        art.download(input_html=html)
        art.parse()
        if len((art.text or "").split()) >= MIN_WORDS:
            return art.text, "newspaper4k"
    except Exception:
        pass
    return text, None


def mentioned(names, text):
    return sorted({n for n in names if re.search(rf"\b{re.escape(n)}\b", text, re.IGNORECASE)})


def main():
    articles = sample_articles()
    members = load_members()
    print(f"Testing {len(articles)} stored articles ({PER_SOURCE} per source, spread across groups)\n")

    stats = defaultdict(Counter)
    failures = Counter()
    body_only_hits = 0

    for a in articles:
        src = a["source"]
        stats[src]["total"] += 1
        print(f"[{src}] {a['group_key']}: {a['title'][:90]}")
        try:
            url = resolve(a)
        except Exception as e:
            print(f"    RESOLVE FAILED: {e}\n")
            failures["resolve failed"] += 1
            continue
        host = urlparse(url).netloc
        print(f"    -> {host}")

        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": BROWSER_UA})
            if resp.status_code != 200:
                print(f"    FETCH FAILED: HTTP {resp.status_code}\n")
                failures[f"HTTP {resp.status_code}"] += 1
                continue
            html = resp.text
        except Exception as e:
            print(f"    FETCH FAILED: {type(e).__name__}\n")
            failures["fetch error"] += 1
            continue

        text, via = extract(url, html)
        if not via:
            print(f"    EXTRACT FAILED: only {len(text.split())} words ({host})\n")
            failures[f"too little text ({host})"] += 1
            continue

        stats[src]["ok"] += 1
        names = members.get(a["group_key"], [])
        in_title = mentioned(names, a["title"])
        in_body = mentioned(names, text)
        extra = [n for n in in_body if n not in in_title]
        if extra:
            body_only_hits += 1
        print(f"    OK via {via}: {len(text.split())} words")
        print(f"    Members in title: {in_title or '-'} | in body: {in_body or '-'}"
              + (f"  <-- body adds {extra}" if extra else ""))
        print(f"    Preview: {' '.join(text.split())[:200]}\n")

        if src == "google_news":
            time.sleep(1)  # don't hammer Google's decoder

    print("=" * 70)
    total_ok = sum(s["ok"] for s in stats.values())
    total = sum(s["total"] for s in stats.values())
    for src, s in stats.items():
        print(f"{src:12s} {s['ok']}/{s['total']} extracted")
    print(f"{'overall':12s} {total_ok}/{total} extracted")
    print(f"Articles where the body names a member the title doesn't: {body_only_hits}/{total_ok}")
    if failures:
        print("Failure reasons: " + ", ".join(f"{k} x{v}" for k, v in failures.most_common()))


if __name__ == "__main__":
    main()

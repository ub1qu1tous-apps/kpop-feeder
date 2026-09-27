"""
Diagnostic only -- not part of the pipeline. For the same sample of
real stored article URLs: try to resolve Google News' redirect to the
actual destination, fetch the page ourselves directly (no third-party
proxy), and run Trafilatura on the raw HTML to see how much clean
article text comes out.
"""

import os

import requests
import trafilatura

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def fetch_sample_articles():
    samples = []
    for source in ["google_news", "bing_news", "soompi"]:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/articles",
            headers=HEADERS,
            params={
                "select": "id,group_key,title,url,source",
                "source": f"eq.{source}",
                "order": "published_at.desc",
                "limit": 2,
            },
            timeout=30,
        )
        resp.raise_for_status()
        samples.extend(resp.json())
    return samples


def resolve_and_fetch(url):
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": BROWSER_UA}, allow_redirects=True)
        return resp.status_code, resp.url, resp.text
    except Exception as e:
        return None, url, str(e)


def main():
    articles = fetch_sample_articles()
    print(f"Testing {len(articles)} sample articles\n")

    for a in articles:
        print(f"=== [{a['source']}] {a['group_key']}: {a['title'][:80]} ===")
        print(f"    Original URL: {a['url'][:100]}")

        status, final_url, html = resolve_and_fetch(a["url"])
        if status != 200:
            print(f"    FETCH FAILED (status={status}): {str(html)[:200]}")
            print()
            continue

        print(f"    Resolved to: {final_url[:120]}")
        print(f"    Fetched {len(html)} chars of raw HTML")

        extracted = trafilatura.extract(html, include_comments=False)
        if not extracted:
            print("    Trafilatura FAILED to extract any text")
        else:
            print(f"    Trafilatura extracted {len(extracted)} chars")
            print(f"    Preview: {extracted[:300].replace(chr(10), ' ')}")
        print()

    print("Done.")


if __name__ == "__main__":
    main()

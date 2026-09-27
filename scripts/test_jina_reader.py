"""
Diagnostic only -- not part of the pipeline. Pulls a handful of real
stored article URLs and tries Jina AI Reader (https://r.jina.ai/) to
see: does it actually fetch the page, how much clean text comes back,
and does searching that text find member mentions the title-only
match missed.
"""

import os
import time

import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


def fetch_sample_articles():
    # A mix: a couple of Google News redirect links, a couple of Bing
    # ones, a couple of direct Soompi links -- different URL shapes.
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


def try_jina_reader(url):
    reader_url = f"https://r.jina.ai/{url}"
    try:
        resp = requests.get(reader_url, timeout=30, headers={"Accept": "text/plain"})
        return resp.status_code, resp.text
    except Exception as e:
        return None, str(e)


def main():
    articles = fetch_sample_articles()
    print(f"Testing {len(articles)} sample articles\n")

    for a in articles:
        print(f"=== [{a['source']}] {a['group_key']}: {a['title'][:80]} ===")
        print(f"    URL: {a['url']}")
        status, text = try_jina_reader(a["url"])
        if status != 200:
            print(f"    FAILED (status={status}): {text[:200]}")
        else:
            print(f"    OK -- {len(text)} chars extracted")
            print(f"    Preview: {text[:300].replace(chr(10), ' ')}")
        print()
        time.sleep(2)  # be polite to the free tier

    print("Done.")


if __name__ == "__main__":
    main()

# Session log

A running record of what's been built, for future reference.

## 2026-09-26 — Initial build

**What it is:** A K-pop news aggregator. Pick a group, see its latest
news (title-only, click through to the source), search/filter by
keyword or date, refresh on demand.

**Architecture**
- Static frontend (`index.html`, `group.html`, `login.html`,
  `admin.html` + `js/`, `css/`) hosted on GitHub Pages, no build step.
- Supabase (Postgres + Auth + Edge Functions) as the backend.
- `groups` table: one row per tracked group (`key`, `display_name`,
  `members`, `search_patterns`, `is_regex`, `last_refreshed_at`).
- `articles` table: one row per article, deduped on
  `(group_key, url)`, never pruned.
- `fetch_status`: single-row status of the last scheduled (all-groups)
  fetch, for the "last updated" / failure banner on the main page.
- `scripts/fetch_and_store.py`: pulls Google News RSS + Bing News RSS
  (per-group search query) and Soompi's feed (title-matched), merges,
  dedupes against 3 days of history, translates non-English titles
  (MyMemory API), extracts publisher name, inserts new rows.
- `.github/workflows/fetch-articles.yml`: runs the fetch every 12h,
  or on-demand for one group (`group_key` input) or all groups.
- `supabase/functions/trigger-fetch`: holds the GitHub token
  server-side, dispatches the workflow, polls it to completion. Public
  per-group mode (10 min cooldown) and admin-only all-groups mode
  (checked via the caller's JWT role claim).

**Sources tried and settled on:** Google News RSS + Bing News RSS
(per-group query, aggregates across many outlets including ones that
block direct scraping) + Soompi's own feed. Dropped: allkpop and
kpopmap (bot-protected, 403/malformed under any user-agent),
koreaportal and whatthekpop (no working feed URL found).

**Features built this session**
- Core pipeline: fetch, dedupe (cross-source + cross-run), store.
- Frontend: group grid, per-group article list with show-more
  (10/20/50/100), date-range search, keyword search.
- Non-English title translation (detect Hangul/Japanese/Chinese
  script, translate via MyMemory, one-time backfill for existing rows).
- Per-group manual refresh button (10 min cooldown, live status).
- Publisher reliability color-coding (green = mainstream press, amber
  = k-pop specialty outlets, red = UGC/tabloid/social, gray =
  unclassified) with a collapsible legend.
- Fetch-status visibility (main page banner if the scheduled fetch
  failed or hasn't run in >14h).
- Admin (single Supabase Auth account, discreet link bottom-right of
  main page): add/edit/delete groups, delete individual articles,
  trigger a full all-groups fetch on demand, status panel.
- Member names: verified rosters for the original 12 groups, stored
  in a dedicated `members` column (separate from `search_patterns`,
  which still carries legacy matching aliases/regex for a few groups).
  Displayed inline beside the group name on its page. New groups can
  auto-lookup members via a Wikipedia scrape (best-effort, admin
  reviews before saving).

**Groups tracked (as of this entry):** ILLIT, LE SSERAFIM, KATSEYE,
IVE, Stray Kids, TXT, Hearts2Hearts, BABYMONSTER, NMIXX, aespa, Twice,
ITZY.

**One-off scripts** (run manually via their own `workflow_dispatch`,
not part of the scheduled pipeline): `backfill_translations.py`,
`backfill_publishers.py`, `backfill_members_column.py`,
`add_member_names.py`.

**Known limitations**
- Publisher extraction is a simple "- Publisher Name" title-suffix
  parse; occasionally wrong (falls back to gray/unclassified, never
  miscategorized as reliable/unreliable).
- Wikipedia member lookup is best-effort; wikitext formatting varies
  page to page.
- `search_patterns` still mixes clean member names with legacy
  aliases/regex for groups seeded before the `members` column existed
  (ive, stray-kids, txt, hearts2hearts) -- harmless for matching, just
  means the raw column isn't a clean list to display from directly
  (use `members` for that).

## 2026-09-27 — Choosing a free article-text extractor

**Goal:** Find a free tool that pulls the full article text (not just the
title) from the links we store, so we can later search article bodies
(e.g. catch member mentions the title-only match misses). Not wired into
the pipeline yet; this was an evaluation only.

**Branch:** `claude/news-scraper-tool-test-iomkov` (no PR opened).

**Added**
- `scripts/test_news_scrapers.py`: self-contained diagnostic (no
  Supabase). Pulls the newest item from the Google News RSS and Bing News
  RSS feeds (same feed URLs as `fetch_and_store.py`), resolves the feed
  link to the publisher URL, fetches the page once, and runs each
  extractor on it. Prints word count, top words and a preview per
  extractor. If a publisher page fails to fetch, it tries the next feed
  item (up to 3). Search term comes from the `QUERY` env var (default
  `aespa`). Exits non-zero if either feed produces no article.
- `.github/workflows/test-news-scrapers.yml`: runs the script. Triggers:
  `workflow_dispatch` (with a `query` input) and push to this branch when
  the script/workflow changes.
- Earlier in the day (previous session, already on this branch's
  history): `test_jina_reader.py` / `test_trafilatura.py` + workflows,
  which test against stored article URLs from Supabase. Their results
  were not reviewed in this session.

**Extractors tested (all free, no API key)**
- trafilatura (pip, Apache-2.0)
- newspaper4k (pip, MIT; maintained fork of newspaper3k; needs
  `lxml_html_clean` installed alongside)
- Jina Reader (hosted: `https://r.jina.ai/<url>`, free tier is
  rate-limited)

**Results** (Actions run 36321033555, query "aespa", passed)

| Feed → article | trafilatura | newspaper4k | Jina Reader |
|---|---|---|---|
| Google → billboard.com, "Where to buy aespa light sticks" | 416 words | 393 words | failed: 403, Billboard blocks Jina |
| Bing → ibtimes.sg, "Rhea Raj, aespa's resurfaced interaction…" | 811 words | 811 words | 869 words (includes photo captions) |

All three return clean article text (no menus/ads). The first Google
item (districtfray.com event page) returned 404 from the publisher, so
the script moved to the second item. trafilatura and newspaper4k both
keep Billboard's affiliate disclaimer at the start of the text.

**Decision / recommendation:** trafilatura as the extractor (most text,
runs locally, no rate limits, no third-party service that sites can
block), newspaper4k as a possible fallback. Jina Reader is not reliable
enough on its own.

**Key technical findings**
- Google News RSS links (`news.google.com/rss/articles/CBMi...`) do not
  point to the publisher. Use `googlenewsdecoder` (pip) to get the real
  URL: `gnewsdecoder(link, interval=1)`. In version 0.2.x the result is
  `{"success": True, "decoded_url": ...}` — the older docs/API used
  `"status"`; checking `status` makes every decode look like a failure
  (that was the bug in the first Actions run). Plain
  `requests.get(..., allow_redirects=True)` on these links, as
  `test_trafilatura.py` does, probably does not reach the publisher
  (not verified this session).
- Bing News RSS links (`bing.com/news/apiclick.aspx?...&url=...`) carry
  the publisher URL in the `url` query parameter; just parse it, no
  request needed.
- Use a browser User-Agent when fetching publisher pages.

**Environment note:** the Claude Code cloud container's network policy
blocks news.google.com, bing.com and publisher sites (proxy returns
403), so these tests cannot run inside the session. Run them on GitHub
Actions instead: push to the branch or dispatch the workflow, then read
the job logs via the GitHub MCP tools (`actions_list` →
`list_workflow_jobs` → `get_job_logs`). Alternatively the user can add
the hosts to the environment's allowed domains (Network access in the
environment settings).

**Suggested next steps**
1. Decide whether to store full article text: add a `body` column (or
   separate table) on `articles`, extract at fetch time in
   `fetch_and_store.py` using googlenewsdecoder + trafilatura, with
   newspaper4k as fallback. Add `trafilatura` and `googlenewsdecoder` to
   `requirements.txt`.
2. Rate-limit the googlenewsdecoder calls (`interval` param); Google may
   throttle bulk decoding.
3. Expect some publisher pages to fail (404/403/paywall); store NULL and
   keep title-only matching as the fallback.
4. Use the body text for member-name matching / keyword search on the
   frontend.
5. Once decided, the diagnostic scripts/workflows (`test_*`) can be
   deleted.

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

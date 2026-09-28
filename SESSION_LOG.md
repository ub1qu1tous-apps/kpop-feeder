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

## 2026-09-27 — Full article text: search + filing by group name

**Why:** titles often don't name the group or members an article is
about; keyword search (e.g. a member name) and "any news mentioning
ILLIT" need the article body.

**Tested first** (dry runs, nothing saved): googlenewsdecoder resolved
30/30 Google links with no rate limiting; trafilatura got full text for
85% of sampled articles (Soompi 10/10, Google 24/30, Bing 17/20), ~1.5s
each. Failing sites: MSN, Chosun, Forbes, allkpop, HoneyPop (title or
summary only). 14 extra group filings in 60 articles, all genuine.
Earliest stored article: 2019-03-21 (TWICE, surfaced by Google search);
collecting started 2026-09-26.

**How it works**
- `supabase/006_article_texts.sql`: `article_texts` table (text stored
  once per link, keyed by `link_key`; a row = "already read"),
  `articles.link_key` + `articles.via_text`, and the `articles_search`
  view (title + summary + body as `search_text`).
- `link_key`: Bing feed links change every fetch (tracking id), so Bing
  uses the real publisher URL from `url=`; Google links minus query
  string; Soompi as-is.
- `scripts/article_text.py`: resolve (googlenewsdecoder / Bing url=),
  fetch with a browser UA, trafilatura text + meta description as
  summary; group-NAME matcher (member names deliberately excluded —
  "Winter", "Han" etc. are everyday words in full text). Names that are
  English words (TWICE, IVE, ...) must be capitalised; others any case
  (so "aespa" matches).
- `fetch_and_store.py`: direct filing unchanged; then every link not in
  `article_texts` is read, saved, and filed under every group it names
  (also groups other than the one being refreshed). Only new links are
  read, so 12h runs and refreshes stay quick. Resolve failures aren't
  saved, so they retry next run. Falls back to titles-only if 006
  hasn't been run.
- `scripts/backfill_article_text.py` (+ workflow "Backfill article
  text"): one-time pass over everything stored; safe to re-run — e.g.
  after adding a new group, to file older articles that mention it.
- Group page: search uses `articles_search.search_text` (falls back to
  title search if the view is missing); "mentioned in article" tag when
  only the body names the group; '"keyword" found in article' tag when
  the keyword isn't in the title. Refresh note now "up to a minute".

**Follow-up (same day): oldest-article cutoff + full group cleanup**
- `supabase/007_cutoff_and_group_cleanup.sql`: `app_settings` single row
  with `oldest_article_date` (default 2026-01-01, admin-editable under
  Settings on admin.html). Fetch and backfill skip anything published
  before it — mainly so a newly added group doesn't pull years-old
  articles from news search. Already-stored older articles are kept.
- Deleting a group already cascaded to its articles; a `before delete`
  trigger on `groups` now also removes stored article text no other
  group uses. Admin delete confirmation says so.

**Go-live results (2026-09-27)**
- Backfill: 349 links read in ~6 min (258 full text, 32 summary only,
  59 title only; 0 unresolved). 89 stored rows older than 2026-01-01
  skipped. 120 extra filings by group name (KATSEYE +20, TWICE +15,
  LE SSERAFIM +15, Stray Kids +13, ILLIT +13, aespa +13, ...).
- First full fetch after: 71 new links read, 24 new rows (19 via text),
  51 pre-cutoff feed entries skipped.
- Immediate second full fetch: "nothing new to read", 0 new rows —
  incremental reading confirmed.

**Decisions made by the user this session**
- File by group name only (not member names) when matching article text.
- File an article under every group it mentions, even if that repeats it
  across group pages.
- Read everything already stored once; after that, scheduled runs and
  refresh read only new links.
- No full text → search falls back to title + summary.
- Oldest article date = hard cutoff for fetching (admin-editable).
- Deleting a group removes its articles and any article text no other
  group uses.
- The 89 stored articles older than 2026-01-01 are kept (not deleted).

**Setup done by the user:** ran 006 + 007 SQL in the Supabase SQL editor
(one combined paste).

**Known limits / how-to**
- MSN, Chosun, Forbes, allkpop, HoneyPop, Chicago Tribune etc. block
  reading → those articles are searchable by title/summary only.
- After adding a new group, run the "Backfill article text" workflow to
  file older stored articles (back to the cutoff date) that mention it.
- A single-group refresh can now take up to ~1 min; if it runs past the
  edge function's 55s poll, the page shows "Still processing…" and the
  new articles appear on the next reload.
- Diagnostic-only scripts/workflows from testing (not part of the
  pipeline): `test_body_extraction`, `test_body_filing_dryrun`,
  `test_trafilatura`, `test_jina_reader`.

## 2026-09-28 — Wikipedia member lookup fix

- "Look up members" couldn't find KiiiKiii: it searched "<name> kpop
  group", which ranked the agency (Starship Entertainment) first; aespa
  had the same weakness (Karina's page ranked first).
- `js/wikipedia.js` now searches the plain name restricted to pages with
  the "Infobox musical artist" template (falls back to a plain search),
  checks the title-matching page first, then up to 3 results until one
  has an infobox members list. This also finds TXT via "Tomorrow X
  Together".
- Verified (GitHub Actions, `test-wikipedia-lookup` diagnostic):
  KiiiKiii, TXT, aespa, TWICE, BABYMONSTER, IVE, ILLIT, Hearts2Hearts,
  Stray Kids, ITZY, NMIXX, LE SSERAFIM and KATSEYE all return members.
- Admin page assets bumped to ?v=10.

**Admin: separate "Other search terms" box (2026-09-28)**
- Problem: the admin page had one box that fed both `members` (shown
  beside the group name) and `search_patterns`, so nicknames like
  "snsd, SNSD" showed up as members.
- Add-group form and each Manage-groups row now have two boxes:
  "Members (shown beside the group name)" and "Other search terms (not
  shown)". Other terms go into `search_patterns` only; they also count
  as group names for article-text filing.
- Saving a row now rebuilds `search_patterns` = name + members + other
  terms: entries still listed keep their stored form (e.g. `\bSKZ\b`),
  entries removed from both boxes are dropped, new ones are added
  (word-bounded for regex groups). Admin assets ?v=11.

**Main page admin link (2026-09-28)**
- Was near-invisible on laptops (dark grey, fixed bottom-right). Now in
  the header at top-right, flush with the right column of group
  buttons, muted colour at 55% opacity, brightens on hover. Confirmed
  by the user on laptop. Assets ?v=9 (index/group/login).

**Girls' Generation low coverage (2026-09-28)**
- Diagnostic (`test-group-news-coverage` workflow): the group was saved
  as "Girl's Generation" (misplaced apostrophe). Google for that exact
  phrase: 2 results since the cutoff; for "Girls' Generation": 86.
  Bing returned 0 for any quoted name with an apostrophe, 5 without.
- Code fixes: title and article-text matching now treat straight and
  curly apostrophes (' ’ ‘) as the same (`article_text.literal_pattern`,
  used by `compile_matcher` too); the Bing query drops apostrophes from
  the group name. User to rename the group to "Girls' Generation" in
  admin.
- Added "Girls' Generation" and "Girls Generation" to the group's search
  terms (new reusable workflow "Add search terms to a group",
  `scripts/add_search_terms.py`; skips terms already present ignoring
  case/apostrophe style; members untouched). Re-ran the backfill: +10
  articles for Girls' Generation (also KiiiKiii +6, TWICE +2, aespa +2,
  Stray Kids +1). Display name still "Girl's Generation" — the news
  search query uses the display name, so renaming it is still the main
  fix.

## 2026-09-28 — Session-log preference

- User asked for a global preference: always keep a session log, and read
  only the session log whenever past info is needed.
- Added `CLAUDE.md` to this repo with that rule (applies to any session
  on kpop-feeder, any device). Gave the user a cloud-environment setup
  script snippet that writes the same rule to `~/.claude/CLAUDE.md` for
  every cloud session, and the same text for `~/.claude/CLAUDE.md` on any
  computer running Claude Code locally.
- Token usage for this session so far (from the transcript): ~0.42M
  output, ~5.35M new input, ~257M cached re-reads (665 steps). Suggested
  starting fresh sessions per feature and relying on this log.
- GitHub access dropped mid-session; user reconnected it.

## 2026-09-28 — Public feedback / group-request board

**What was added:** a "Feedback / request a group" button, top-right of
the main page (next to, but visually distinct from, the discreet admin
link -- this one is meant to be noticed). It leads to a new page,
`feedback.html`: a textarea to post, and a public list of everything
posted so far (newest first, no login needed to read or post).

**Decisions made by the user this session**
- Anonymous, no accounts -- anyone can post, everyone sees the same list.
- Each entry has a status: `Open` (default) or `Done`. Only the admin can
  change it (from the new Feedback panel on admin.html) or delete an
  entry.
- Whole list shown, no pagination, capped at 20 entries -- when a 21st
  comes in, the oldest is dropped automatically (my default, confirmed
  by not objecting; the alternative -- blocking new posts once full --
  was rejected as worse for spam bursts).

**How it works**
- `supabase/008_feedback.sql`: `feedback` table (`message`, `status`
  `open`/`done`, `created_at`). RLS: public read, public insert (checked
  to always land as `status = 'open'`, so a visitor can't post directly
  as Done), authenticated (admin) update/delete. An `after insert`
  trigger (`security definer`, same pattern as the group-delete cleanup
  trigger) deletes everything past the 20 most recent rows.
- `feedback.html` + `js/feedback.js`: textarea + submit, list below with
  a status badge per entry.
- `admin.html` + `js/admin.js`: new "Feedback" panel, same place as
  Manage groups -- each entry with a "Mark Open/Done" toggle and Delete,
  same confirm-before-delete pattern as group deletion.
- Assets bumped to `?v=12` on every page (shared `css/style.css` changed).

**Setup needed from the user:** run `supabase/008_feedback.sql` in the
Supabase SQL editor before this goes live -- the feedback page will
otherwise show a "Failed to load" error (table doesn't exist yet).

**Known limits**
- No spam protection beyond the 20-entry cap and Supabase's own rate
  limits -- no CAPTCHA, no per-visitor throttle. Revisit if it gets
  abused.
- Message length capped at 2000 characters (DB constraint), not
  surfaced anywhere in the UI besides the textarea's `maxlength`.

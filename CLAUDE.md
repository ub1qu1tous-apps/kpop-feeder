# Session log (always)

- Every project keeps a `SESSION_LOG.md` at the repository root. Create it
  if it doesn't exist.
- After each meaningful piece of work (a feature, fix, decision, setup
  step the user did, or test result), append a dated entry summarising
  what was done, why, the decisions made, and anything left open. Commit
  it together with the work.
- Whenever past information is needed (what was built before, earlier
  decisions, previous sessions), read `SESSION_LOG.md` only. Do not dig
  through old transcripts or git history for it. If the log doesn't
  cover something, say so and ask.

# Preferences

## Code requests
When asked for code, don't write it straight away. First summarize the
request, ask clarifying questions if anything's missing, and give 3
brief suggestions to improve it. Only write the code once the user
confirms they're ready.

## Short forms
The user uses short forms, e.g. "u" for "you", "yr" for "your". If an
unfamiliar one shows up, ask what it means, then save it below once
confirmed.

Known short forms:
- u = you
- yr = your
- r = are
- wat = what
- tis = this

## Free tools first
Any recommendation involving external software should be free to use
or download by default. If a paid tool would be the best fit, ask the
user first before recommending it. The user currently only pays for
Claude Pro.

"""
One-off admin helper: add extra search terms (other spellings, nicknames)
to a group's search_patterns. They are used for matching only -- the
members list (shown on the group page) is not touched. Terms already
present (ignoring case and apostrophe style) are skipped.

Env: GROUP_KEY, TERMS (separated by |)
"""

import os
import re

import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def comparable(term):
    plain = term.replace("\\b", "").replace("\\", "")
    return re.sub("['’‘]", "'", plain).lower()


def main():
    group_key = os.environ["GROUP_KEY"].strip()
    terms = [t.strip() for t in os.environ["TERMS"].split("|") if t.strip()]

    rows = requests.get(
        f"{SUPABASE_URL}/rest/v1/groups", headers=HEADERS,
        params={"key": f"eq.{group_key}", "select": "display_name,search_patterns,is_regex,members"}, timeout=30,
    ).json()
    if not rows:
        raise SystemExit(f"No group with key {group_key!r}")
    group = rows[0]
    patterns = group["search_patterns"]
    print(f"{group['display_name']} ({group_key})")
    print(f"  members (unchanged): {group.get('members')}")
    print(f"  search terms before: {patterns}")

    have = {comparable(p) for p in patterns}
    added = []
    for t in terms:
        if comparable(t) in have:
            continue
        have.add(comparable(t))
        added.append(rf"\b{re.escape(t)}\b" if group["is_regex"] else t)

    if not added:
        print("  nothing to add -- all terms already present")
        return
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/groups", headers={**HEADERS, "Prefer": "return=minimal"},
        params={"key": f"eq.{group_key}"}, json={"search_patterns": patterns + added}, timeout=30,
    )
    resp.raise_for_status()
    print(f"  added: {added}")
    print(f"  search terms after: {patterns + added}")


if __name__ == "__main__":
    main()

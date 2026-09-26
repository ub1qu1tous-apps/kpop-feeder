"""
One-off: populate the new `members` column with the clean roster for
each group, separate from search_patterns (which still has legacy
aliases/regex fragments like "\\bTXT\\b" mixed in from earlier
migrations -- those stay put, unaffected, for matching purposes).
"""

import os

import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

MEMBERS = {
    "illit": ["Yunah", "Minju", "Moka", "Wonhee", "Iroha"],
    "le-sserafim": ["Sakura", "Chaewon", "Yunjin", "Kazuha", "Eunchae"],
    "katseye": ["Daniela", "Lara", "Manon", "Megan", "Sophia", "Yoonchae"],
    "ive": ["Gaeul", "Yujin", "Rei", "Liz", "Leeseo", "Wonyoung"],
    "stray-kids": ["Bang Chan", "Lee Know", "Changbin", "Hyunjin", "Han", "Felix", "Seungmin", "I.N"],
    "txt": ["Soobin", "Yeonjun", "Beomgyu", "Taehyun", "Huening Kai"],
    "hearts2hearts": ["Carmen", "Jiwoo", "Yuha", "Stella", "Juun", "A-na", "Ian", "Ye-on"],
    "babymonster": ["Ruka", "Pharita", "Asa", "Ahyeon", "Rami", "Rora", "Chiquita"],
    "nmixx": ["Lily", "Haewon", "Sullyoon", "Bae", "Jiwoo", "Kyujin"],
    "aespa": ["Karina", "Giselle", "Winter", "Ningning"],
    "twice": ["Nayeon", "Jeongyeon", "Momo", "Sana", "Jihyo", "Mina", "Dahyun", "Chaeyoung", "Tzuyu"],
    "itzy": ["Yeji", "Lia", "Ryujin", "Chaeryeong", "Yuna"],
}


def main():
    for key, members in MEMBERS.items():
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/groups",
            headers={**HEADERS, "Prefer": "return=minimal"},
            params={"key": f"eq.{key}"},
            json={"members": members},
            timeout=30,
        )
        resp.raise_for_status()
        print(f"  {key}: set members = {members}")

    print("Done.")


if __name__ == "__main__":
    main()

"""
Shared helper: detect non-English article titles (Korean/Japanese/Chinese
script) and translate just the title text to English via MyMemory's free
translation API (no API key needed). The article link is left untouched
-- clicking through, the browser's own page-translate handles the body.
"""

import re

import requests

HANGUL_RE = re.compile(r"[가-힣]")
KANA_RE = re.compile(r"[぀-ヿ]")  # hiragana + katakana
CJK_RE = re.compile(r"[一-鿿]")  # CJK unified ideographs (hanja/kanji/hanzi)


def detect_source_lang(text):
    if HANGUL_RE.search(text):
        return "ko"
    if KANA_RE.search(text):
        return "ja"
    if CJK_RE.search(text):
        return "zh"
    return None  # already Latin script -- assume English, nothing to do


def translate_to_english(text, source_lang):
    try:
        resp = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": f"{source_lang}|en"},
            timeout=15,
        )
        resp.raise_for_status()
        translated = resp.json().get("responseData", {}).get("translatedText")
        return translated or text
    except Exception:
        return text  # translation failure shouldn't block ingesting the article


def maybe_translate_title(title):
    lang = detect_source_lang(title)
    if not lang:
        return title
    return translate_to_english(title, lang)

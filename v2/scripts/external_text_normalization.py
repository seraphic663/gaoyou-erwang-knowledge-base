"""Conservative text normalization for public-source locating candidates.

This module is intentionally a locating aid only.  It does not normalize a
canonical source, choose an edition, or authorize a quote check.
"""

from __future__ import annotations

import html
import re
import unicodedata


# This is a deliberately small, auditable map.  It covers the characters
# occurring in the current public candidate queue; it is not a general
# simplified/traditional conversion table.
SIMPLIFIED_TO_TRADITIONAL = {
    "礼": "禮",
    "记": "記",
    "书": "書",
    "传": "傳",
    "说": "說",
    "广": "廣",
    "雅": "雅",
    "势": "勢",
    "义": "義",
    "乐": "樂",
    "乱": "亂",
    "国": "國",
    "声": "聲",
    "风": "風",
    "电": "電",
    "与": "與",
    "为": "為",
    "也": "也",
    "文": "文",
    "尔": "爾",
    "东": "東",
    "仪": "儀",
    "乡": "鄉",
    "射": "射",
    "齐": "齊",
    "鲁": "魯",
    "经": "經",
    "论": "論",
    "语": "語",
    "诗": "詩",
    "击": "擊",
    "鼓": "鼓",
    "邱": "邱",
    "采": "採",
    "苹": "蘋",
    "韩": "韓",
    "奕": "奕",
    "苑": "苑",
    "慎": "慎",
    "汉": "漢",
    "将": "將",
    "军": "軍",
    "伤": "傷",
    "创": "創",
    "疥": "疥",
    "癣": "癬",
    "旧": "舊",
    "简": "簡",
    "标": "標",
    "识": "識",
    "远": "遠",
    "举": "舉",
    "顾": "顧",
    "忧": "憂",
    "温": "溫",
    "润": "潤",
    "泽": "澤",
    "缜": "縝",
    "孙": "孫",
    "难": "難",
    "劝": "勸",
    "对": "對",
    "扬": "揚",
    "于": "於",
    "贤": "賢",
    "尝": "嘗",
    "宾": "賓",
    "门": "門",
    "虑": "慮",
    "谏": "諫",
    "数": "數",
    "狱": "獄",
    "赋": "賦",
    "卒": "卒",
    "浅": "淺",
    "厉": "厲",
    "灵": "靈",
    "辞": "辭",
}

TRANSLATION_TABLE = str.maketrans(SIMPLIFIED_TO_TRADITIONAL)


def strip_wikitext(raw_text: str) -> str:
    """Expose a conservative readable view of a frozen Wikitext page.

    The raw Wikitext remains the evidence-bearing candidate artifact.  This
    view only removes page markup and known annotation templates so that a
    locating search is not defeated by ``ProperNoun`` or ``SKnotes`` markup.
    """

    text = re.sub(r"<!--.*?-->", "", raw_text or "", flags=re.DOTALL)
    text = re.sub(r"<ref\b[^>]*>.*?</ref\s*>", "", text, flags=re.I | re.DOTALL)
    text = re.sub(r"</?(?:onlyinclude|poem|nowiki|center|div|br)\b[^>]*>", "", text, flags=re.I)
    text = re.sub(r"\{\{\s*SK\s+anchor\s*\|([^{}|]*)\}\}", r"\1", text, flags=re.I)
    text = re.sub(
        r"\{\{\s*(?:SK\s+char|SK\s+notes|SK\s+QS|header2?|pages)\b[^{}]*\}\}",
        "",
        text,
        flags=re.I,
    )
    # Resolve simple, non-nested templates repeatedly.  ProperNoun-like
    # templates retain their first argument; note/formatting templates are
    # otherwise removed or reduced conservatively.
    for _ in range(5):
        updated = re.sub(r"\{\{\s*[^{}|]+\|([^{}|]*)\}\}", r"\1", text)
        updated = re.sub(r"\{\{[^{}]*\}\}", "", updated)
        if updated == text:
            break
        text = updated
    text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"-\{([^{}]*)\}-", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return unicodedata.normalize("NFKC", html.unescape(text)).strip()


def compact_for_match(value: str) -> str:
    """Compact text for locating only; preserve the original text elsewhere."""

    value = unicodedata.normalize("NFKC", value or "").translate(TRANSLATION_TABLE)
    return "".join(
        char
        for char in value
        if not unicodedata.category(char).startswith(("P", "Z"))
        and unicodedata.category(char) != "Cf"
    )


def normalized_contiguous_match(raw_text: str, quote: str) -> tuple[bool, int | None, int | None]:
    """Return whether quote occurs contiguously in the cleaned candidate text."""

    candidate = compact_for_match(strip_wikitext(raw_text))
    needle = compact_for_match(quote)
    if not needle:
        return False, None, None
    start = candidate.find(needle)
    if start < 0:
        return False, None, None
    return True, start, start + len(needle)

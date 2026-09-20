"""Read-only passage retrieval for the V2 corpus.

The bridge deliberately returns only canonical source passages.  It does not
turn a match into an evidence approval, and it never writes to the database.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


TOKEN_SPLIT_RE = re.compile(r"[\s,，。；;、？！!?：:/|]+")
SIMPLIFIED_TO_TRADITIONAL = str.maketrans({
    "于": "於", "为": "爲", "后": "後", "说": "說", "释": "釋",
    "经": "經", "传": "傳", "证": "證", "学": "學", "书": "書",
    "杂": "雜", "闻": "聞", "义": "義", "词": "詞", "语": "語",
    "论": "論", "说": "說", "会": "會", "过": "過", "从": "從",
    "并": "並", "与": "與", "无": "無", "为": "爲", "这": "這",
    "个": "個", "见": "見", "现": "現", "长": "長", "门": "門",
    "国": "國", "体": "體", "发": "發", "开": "開", "间": "間",
    "点": "點", "当": "當", "来": "來", "实": "實", "对": "對",
    "应": "應", "过": "過", "难": "難", "还": "還", "断": "斷",
    "读": "讀", "写": "寫", "类": "類", "变": "變", "别": "別",
    "内": "內", "气": "氣", "声": "聲", "质": "質", "问": "問",
    "标": "標", "题": "題", "录": "錄", "页": "頁", "处": "處",
    "见": "見", "遗": "遺", "为": "爲", "归": "歸", "并": "並",
})


def normalize(value: Any) -> str:
    return re.sub(r"[ \t\r\n]+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def traditional_variant(value: str) -> str:
    return normalize(value).translate(SIMPLIFIED_TO_TRADITIONAL)


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"V2 corpus database not found: {db_path}")
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def query_tokens(query: str) -> list[str]:
    normalized = normalize(query)
    pieces = [piece for piece in TOKEN_SPLIT_RE.split(normalized) if len(piece) >= 2]
    return list(dict.fromkeys(pieces or ([normalized] if len(normalized) >= 2 else [])))[:12]


def excerpt_around_match(text: str, tokens: list[str], limit: int = 2400) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    variant_text = traditional_variant(text)
    positions = []
    for token in tokens:
        positions.extend(position for position in (text.find(token), variant_text.find(traditional_variant(token))) if position >= 0)
    if not positions:
        return text[:limit], True
    center = min(positions)
    start = max(0, center - (limit // 2))
    end = min(len(text), start + limit)
    start = max(0, end - limit)
    prefix = "" if start == 0 else "……"
    suffix = "" if end == len(text) else "……"
    return f"{prefix}{text[start:end]}{suffix}", True


def retrieve(
    connection: sqlite3.Connection,
    *,
    query: str,
    work_key: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    normalized_query = normalize(query)
    tokens = query_tokens(normalized_query)
    if not tokens:
        return {
            "ok": True,
            "query": normalized_query,
            "work_key": work_key,
            "candidate_count": 0,
            "items": [],
            "trace": {"canonical_only": True, "reason": "empty_query"},
        }

    search_tokens = list(dict.fromkeys([*tokens, *(traditional_variant(token) for token in tokens)]))
    conditions = []
    condition_parameters: list[Any] = []
    for token in search_tokens:
        conditions.append("(p.normalized_text LIKE ? OR p.plain_text LIKE ? OR p.entry_title LIKE ?)")
        needle = f"%{token}%"
        condition_parameters.extend([needle, needle, needle])
    parameters: list[Any] = []
    work_clause = ""
    if work_key:
        work_clause = " AND (p.work_key = ? OR sd.work_key = ?)"
        parameters.extend([work_key, work_key])
    parameters.extend(condition_parameters)

    rows = connection.execute(
        f"""
        SELECT p.passage_id, p.source_document_id, p.work_key,
               p.document_title, p.section_title, p.entry_title,
               p.local_ordinal, p.md_line_start, p.md_line_end,
               p.raw_text, p.plain_text, p.normalized_text,
               sd.source_file, sd.source_kind, sd.canonical_status
        FROM passages p
        JOIN source_documents sd ON sd.source_document_id = p.source_document_id
        WHERE sd.canonical_status = 'canonical_active'
          {work_clause}
          AND ({' OR '.join(conditions)})
        LIMIT 500
        """,
        parameters,
    ).fetchall()

    ranked = []
    for row in rows:
        item = dict(row)
        text = normalize(item.get("normalized_text") or item.get("plain_text"))
        entry_title = normalize(item.get("entry_title"))
        text_variant = traditional_variant(text)
        entry_title_variant = traditional_variant(entry_title)
        score = 0
        reasons: list[str] = []
        for token in tokens:
            if not token:
                continue
            direct_text = token in text
            variant_text = traditional_variant(token) in text_variant
            direct_title = token in entry_title
            variant_title = traditional_variant(token) in entry_title_variant
            if direct_text or variant_text:
                score += 100 + min(len(token), 12)
                reasons.append("完整短语命中" if direct_text else "简繁字形转换后命中")
            if direct_title or variant_title:
                score += 40
                reasons.append("篇目标题命中")
        if not reasons:
            reasons.append("正文片段命中")
        item["score"] = score
        item["match_reason"] = "；".join(dict.fromkeys(reasons))
        passage_text = item.pop("plain_text") or item.get("raw_text") or ""
        item.pop("raw_text", None)
        item.pop("normalized_text", None)
        item["passage_text"], item["text_truncated"] = excerpt_around_match(passage_text, tokens)
        ranked.append(item)

    ranked.sort(key=lambda item: (-int(item["score"]), str(item.get("passage_id") or "")))
    best_score = int(ranked[0]["score"]) if ranked else 0
    score_floor = max(0, best_score - 24)
    relevant = [item for item in ranked if int(item["score"]) >= score_floor]
    items = relevant[: max(1, min(int(limit), 20))]
    return {
        "ok": True,
        "query": normalized_query,
        "work_key": work_key,
        "candidate_count": len(rows),
        "returned_count": len(items),
        "items": items,
        "trace": {
            "canonical_only": True,
            "source_kinds": sorted({str(item.get("source_kind") or "") for item in items}),
            "retrieval_method": "normalized_substring_ranked_with_match_window",
            "score_floor": score_floor,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("retrieve",))
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--work-key", default="")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    try:
        connection = connect(args.db)
        try:
            payload = retrieve(
                connection,
                query=args.query,
                work_key=args.work_key,
                limit=args.limit,
            )
        finally:
            connection.close()
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "message": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

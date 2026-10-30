"""Read-only passage retrieval for the shared corpus.

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
        raise FileNotFoundError(f"Corpus database not found: {db_path}")
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def is_single_han_character(value: str) -> bool:
    if len(value) != 1:
        return False
    name = unicodedata.name(value, "")
    return name.startswith(("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-"))


def query_tokens(query: str, *, allow_single_character: bool = False) -> list[str]:
    normalized = normalize(query)
    pieces = [
        piece for piece in TOKEN_SPLIT_RE.split(normalized)
        if len(piece) >= 2 or (allow_single_character and is_single_han_character(piece))
    ]
    return list(dict.fromkeys(pieces))[:12]


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


def attach_related_cases(
    connection: sqlite3.Connection,
    items: list[dict[str, Any]],
) -> None:
    """Attach lightweight case links without exposing case JSON.

    Passage retrieval remains the ranked operation.  The case links are only
    a navigation aid for the website: a passage can be linked from a case's
    source passage, an evidence passage, or both.
    """
    passage_ids = [str(item.get("passage_id") or "") for item in items if item.get("passage_id")]
    if not passage_ids:
        return
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('annotation_cases', 'annotation_evidences')"
        ).fetchall()
    }
    if "annotation_cases" not in tables:
        return

    placeholders = ",".join("?" for _ in passage_ids)
    if "annotation_evidences" in tables:
        rows = connection.execute(
            f"""
            SELECT c.case_id, c.case_title, c.source_work, c.target_work, c.target_text,
                   c.machine_status, c.human_status, c.source_passage_id,
                   e.passage_id AS evidence_passage_id
            FROM annotation_cases c
            LEFT JOIN annotation_evidences e ON e.case_id = c.case_id
            WHERE c.source_passage_id IN ({placeholders})
               OR e.passage_id IN ({placeholders})
            ORDER BY c.case_title, c.case_id
            """,
            [*passage_ids, *passage_ids],
        ).fetchall()
    else:
        rows = connection.execute(
            f"""
            SELECT c.case_id, c.case_title, c.source_work, c.target_work, c.target_text,
                   c.machine_status, c.human_status, c.source_passage_id,
                   NULL AS evidence_passage_id
            FROM annotation_cases c
            WHERE c.source_passage_id IN ({placeholders})
            ORDER BY c.case_title, c.case_id
            """,
            passage_ids,
        ).fetchall()

    related: dict[str, dict[str, dict[str, Any]]] = {passage_id: {} for passage_id in passage_ids}
    for row in rows:
        record = dict(row)
        case_id = str(record.get("case_id") or "")
        if not case_id:
            continue
        for passage_id in passage_ids:
            roles: list[str] = []
            if record.get("source_passage_id") == passage_id:
                roles.append("source_passage")
            if record.get("evidence_passage_id") == passage_id:
                roles.append("evidence")
            if not roles:
                continue
            current = related[passage_id].setdefault(case_id, {
                "case_id": case_id,
                "case_title": record.get("case_title") or "未命名案例",
                "source_work": record.get("source_work") or "",
                "target_work": record.get("target_work") or "",
                "target_text": record.get("target_text") or "",
                "machine_status": record.get("machine_status") or "",
                "human_status": record.get("human_status") or "",
                "relations": [],
            })
            current["relations"] = list(dict.fromkeys([*current["relations"], *roles]))

    for item in items:
        passage_id = str(item.get("passage_id") or "")
        cases = list(related.get(passage_id, {}).values())
        for case in cases:
            case["relations"] = sorted(case["relations"])
        item["related_cases"] = cases


def retrieve(
    connection: sqlite3.Connection,
    *,
    query: str,
    work_key: str = "",
    work_keys: list[str] | None = None,
    limit: int = 8,
    offset: int = 0,
    include_cases: bool = False,
    search_mode: str = "unified",
    allow_single_character: bool = False,
    query_match: str = "all",
) -> dict[str, Any]:
    if search_mode not in {"unified", "body", "title"}:
        raise ValueError("invalid_search_mode")
    if query_match not in {"all", "any"}:
        raise ValueError("invalid_query_match")
    normalized_query = normalize(query)
    tokens = query_tokens(normalized_query, allow_single_character=allow_single_character)
    single_character_search = allow_single_character and len(tokens) == 1 and is_single_han_character(tokens[0])
    selected_work_keys = list(dict.fromkeys(
        str(value).strip() for value in (work_keys or []) if str(value).strip()
    ))
    if not selected_work_keys and work_key:
        selected_work_keys = [work_key]
    page_size = max(1, min(int(limit), 20))
    requested_offset = max(0, min(int(offset), 100000))
    if not tokens:
        reason = "single_character_search_disabled" if is_single_han_character(normalized_query) else "empty_query"
        return {
            "ok": True,
            "query": normalized_query,
            "work_key": work_key or (selected_work_keys[0] if len(selected_work_keys) == 1 else ""),
            "work_keys": selected_work_keys,
            "search_mode": search_mode,
            "query_match": query_match,
            "allow_single_character": allow_single_character,
            "candidate_count": 0,
            "candidate_count_capped": False,
            "result_count": 0,
            "offset": 0,
            "limit": page_size,
            "returned_count": 0,
            "items": [],
            "trace": {"canonical_only": True, "reason": reason},
        }

    conditions = []
    condition_parameters: list[Any] = []
    for token in tokens:
        variants = list(dict.fromkeys([token, traditional_variant(token)]))
        variant_conditions = []
        for variant in variants:
            needle = f"%{variant}%"
            fields = []
            if search_mode in {"unified", "body"}:
                fields.extend(["p.normalized_text LIKE ?", "p.plain_text LIKE ?"])
                condition_parameters.extend([needle, needle])
            if search_mode in {"unified", "title"}:
                fields.extend([
                    "p.document_title LIKE ?", "p.section_title LIKE ?", "p.entry_title LIKE ?",
                ])
                condition_parameters.extend([needle, needle, needle])
            variant_conditions.append("(" + " OR ".join(fields) + ")")
        conditions.append("(" + " OR ".join(variant_conditions) + ")")
    parameters: list[Any] = []
    work_clause = ""
    if selected_work_keys:
        placeholders = ", ".join("?" for _ in selected_work_keys)
        work_clause = f" AND (p.work_key IN ({placeholders}) OR sd.work_key IN ({placeholders}))"
        parameters.extend([*selected_work_keys, *selected_work_keys])
    parameters.extend(condition_parameters)

    row_limit_clause = "" if single_character_search else "LIMIT 500"
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
          AND ({' AND '.join(conditions) if query_match == 'all' else ' OR '.join(conditions)})
          {row_limit_clause}
        """,
        parameters,
    ).fetchall()

    ranked = []
    for row in rows:
        item = dict(row)
        text = normalize(item.get("normalized_text") or item.get("plain_text"))
        title = normalize(" ".join(filter(None, [
            item.get("document_title"), item.get("section_title"), item.get("entry_title"),
        ])))
        text_variant = traditional_variant(text)
        title_variant = traditional_variant(title)
        score = 0
        reasons: list[str] = []
        matched_terms: list[str] = []
        for token in tokens:
            if not token:
                continue
            direct_text = search_mode != "title" and token in text
            variant_text = search_mode != "title" and traditional_variant(token) in text_variant
            direct_title = search_mode != "body" and token in title
            variant_title = search_mode != "body" and traditional_variant(token) in title_variant
            if direct_text or variant_text:
                score += 100 + min(len(token), 12)
                reasons.append("完整短语命中" if direct_text else "简繁字形转换后命中")
            if direct_title or variant_title:
                score += 140 + min(len(token), 12)
                reasons.append("篇目标题命中")
            if direct_text or variant_text or direct_title or variant_title:
                matched_terms.append(token)
        if not reasons:
            reasons.append("正文片段命中")
        item["score"] = score
        item["match_reason"] = "；".join(dict.fromkeys(reasons))
        item["matched_terms"] = list(dict.fromkeys(matched_terms))
        passage_text = item.pop("plain_text") or item.get("raw_text") or ""
        item.pop("raw_text", None)
        item.pop("normalized_text", None)
        item["passage_text"], item["text_truncated"] = excerpt_around_match(passage_text, tokens)
        ranked.append(item)

    ranked.sort(key=lambda item: (-int(item["score"]), str(item.get("passage_id") or "")))
    best_score = int(ranked[0]["score"]) if ranked else 0
    score_floor = max(0, best_score - 24)
    relevant = [item for item in ranked if int(item["score"]) >= score_floor]
    result_items = ranked if single_character_search or len(tokens) > 1 else relevant
    result_count = len(result_items)
    if result_count:
        last_page_offset = ((result_count - 1) // page_size) * page_size
        page_offset = min(requested_offset, last_page_offset)
    else:
        page_offset = 0
    items = result_items[page_offset:page_offset + page_size]
    if include_cases:
        attach_related_cases(connection, items)
    return {
        "ok": True,
        "query": normalized_query,
        "work_key": work_key or (selected_work_keys[0] if len(selected_work_keys) == 1 else ""),
        "work_keys": selected_work_keys,
        "search_mode": search_mode,
        "query_match": query_match,
        "allow_single_character": allow_single_character,
        "candidate_count": len(rows),
        "candidate_count_capped": not single_character_search and len(rows) >= 500,
        "result_count": result_count,
        "offset": page_offset,
        "limit": page_size,
        "returned_count": len(items),
        "items": items,
        "trace": {
            "canonical_only": True,
            "source_kinds": sorted({str(item.get("source_kind") or "") for item in items}),
            "retrieval_method": "normalized_substring_ranked_with_match_window",
            "score_floor": None if single_character_search else score_floor,
            "single_character_all_matches": single_character_search,
            "query_match": query_match,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("retrieve",))
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--work-key", default="")
    parser.add_argument("--work-keys", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--include-cases", action="store_true")
    parser.add_argument("--search-mode", choices=("unified", "body", "title"), default="unified")
    parser.add_argument("--allow-single-character", action="store_true")
    parser.add_argument("--query-match", choices=("all", "any"), default="all")
    args = parser.parse_args()

    try:
        connection = connect(args.db)
        try:
            payload = retrieve(
                connection,
                query=args.query,
                work_key=args.work_key,
                work_keys=[value for value in args.work_keys.split(",") if value],
                limit=args.limit,
                offset=args.offset,
                include_cases=args.include_cases,
                search_mode=args.search_mode,
                allow_single_character=args.allow_single_character,
                query_match=args.query_match,
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

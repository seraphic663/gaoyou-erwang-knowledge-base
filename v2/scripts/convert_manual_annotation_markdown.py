"""Convert case-level Markdown notes into auditable V2 JSONL candidates.

This script is intentionally read-only with respect to the V2 database. It
extracts only explicit Markdown structure, records source spans and hashes,
and marks unsupported fields for review instead of guessing them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    from jsonschema import Draft202012Validator as JSON_SCHEMA_VALIDATOR

    SCHEMA_VALIDATION_METHOD = "jsonschema_draft_2020_12"
except ImportError:
    JSON_SCHEMA_VALIDATOR = None
    SCHEMA_VALIDATION_METHOD = "built_in_schema_checks"


ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = ROOT / "v2"
DEFAULT_SOURCE_DIR = ROOT / "04-项目文献" / "0-当前阅读" / "annotation"
DEFAULT_DATABASE = V2_ROOT / "data" / "real_runs" / "annotation_v2.db"
DEFAULT_OUTPUT_DIR = V2_ROOT / "data" / "real_runs" / "manual_annotation_ingress"
SCHEMA_PATH = V2_ROOT / "schemas" / "annotation_case.v1.schema.json"

SOURCE_WORK_KEYS = {
    "读书杂志": "dushu_zazhi",
    "广雅疏证": "guangya_shuzheng",
    "经义述闻": "jingyi_shuwen",
    "经传释词": "jingzhuan_shici",
}

SECTION_ALIASES = {
    "考據對象": "target_text",
    "考据对象": "target_text",
    "反駁對象": "counter_argument",
    "反驳对象": "counter_argument",
    "論點": "claim",
    "论点": "claim",
    "字詞關係": "term_relations",
    "字词关系": "term_relations",
    "引用書證": "evidence_text",
    "引用书证": "evidence_text",
    "引用文獻": "evidence_text",
    "引用文献": "evidence_text",
    "運用術語": "method_terms",
    "运用术语": "method_terms",
    "考據用語": "method_terms",
    "考据用语": "method_terms",
    "訓詁術語": "method_terms",
    "训诂术语": "method_terms",
    "考據過程": "process_text",
    "考据过程": "process_text",
    "結論": "conclusion",
    "结论": "conclusion",
    "整體考據總結": "overall_summary",
    "整体考据总结": "overall_summary",
    "虛詞義項": "lexical_items",
    "虚词义项": "lexical_items",
    "原論述（原文摘錄）": "source_argument",
    "原论述（原文摘录）": "source_argument",
    "共同背景（原文摘錄）": "shared_background",
    "共同背景（原文摘录）": "shared_background",
    "對應義項（原文摘錄）": "lexical_items",
    "对应义项（原文摘录）": "lexical_items",
}

PROCESS_LABELS = {
    "發疑": "problem_discovery",
    "发疑": "problem_discovery",
    "預設": "research_question",
    "预设": "research_question",
    "立論": "research_question",
    "立论": "research_question",
    "取證": "evidence_collection",
    "取证": "evidence_collection",
    "釋理": "reasoning",
    "释理": "reasoning",
    "結論": "conclusion",
    "结论": "conclusion",
}

QUOTE_RE = re.compile(
    r"「([^「」\n]+)」|“([^“”\n]+)”|『([^『』\n]+)』|"
    r"‘([^‘’\n]+)’|\"([^\"\n]+)\""
)
ARROW_CHAIN_RE = re.compile(
    r"[\u3400-\u9fffA-Za-z0-9“”「」『』‘’]+"
    r"(?:\s*(?:↔|⇄|→|⇒|＝|=)\s*[\u3400-\u9fffA-Za-z0-9“”「」『』‘’]+)+"
)
QUOTED_RELATION_RE = re.compile(
    r"[“「『‘]([^”」』’]{1,12})[”」』’]\s*"
    r"(當作|当作|當為|当为|訓為|训为|訓爲|训爲|讀為|读为|讀爲|读爲|通|猶|犹|指|作)\s*"
    r"[“「『‘]?([^”」』’：:，,。；;]{1,24})[”」』’]?"
)
BARE_RELATION_RE = re.compile(
    r"^\s*[“「『]?([\u3400-\u9fffA-Za-z0-9]{1,8})[”」』]?\s*"
    r"(?:當作|当作|當為|当为|訓為|训为|訓爲|训爲|讀為|读为|讀爲|读爲|通|猶|犹|指|作)\s*"
    r"[“「『]?([\u3400-\u9fffA-Za-z0-9]{1,16})[”」』]?"
)
UNQUOTED_RELATION_RE = re.compile(
    r"(?<![\u3400-\u9fff])([\u3400-\u9fff]{1,4})\s*"
    r"(譌為|讹为|當作|当作|當為|当为|訓為|训为|訓爲|训爲|讀為|读为|讀爲|读爲|通)\s*"
    r"[“「『‘]?([\u3400-\u9fff]{1,8})[”」』’]?"
)
VIRTUAL_GLOSS_RE = re.compile(
    r"(?:義項[^：:\n]*[：:]\s*)?[“「『‘]?([\u3400-\u9fff]{1,6})[”」』’]?\s*[，,、]?\s*"
    r"(?:猶|犹|訓為|训为|訓爲|训爲|為|为)?\s*[“「『‘]?"
    r"(語辭|语辞|語詞|语词|發語詞|发语词|語助詞|语助词|指事之詞|指示詞|副詞|连词|連詞)[”」』’]?"
)
SOUND_RELATION_RE = re.compile(
    r"[“‘「『]([^”’」』]{1,8})[”’」』]\s*[、，,]\s*"
    r"[“‘「『]([^”’」』]{1,8})[”’」』]\s*(?:語之轉|语之转|聲近|声近|音近)"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(value: str) -> str:
    try:
        from erwang_v2.markdown_preprocess import normalize_for_match

        return normalize_for_match(value)
    except Exception:
        import unicodedata

        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def compact_key(value: str) -> str:
    return "".join(character for character in normalize_text(value) if character.isalnum())


def parse_filename(path: Path) -> dict[str, str]:
    pieces = path.stem.split("-")
    if len(pieces) < 5:
        raise ValueError(f"filename does not match ID-work-object-phrase-author: {path.name}")
    case_id, source_work, target_label = pieces[:3]
    annotator = pieces[-1]
    phrase = "-".join(pieces[3:-1])
    if not re.fullmatch(r"\d{3}[A-Z]?", case_id):
        raise ValueError(f"invalid case ID in filename: {path.name}")
    return {
        "case_id": case_id,
        "source_id": case_id[:3],
        "source_work": source_work,
        "target_label": target_label,
        "case_phrase": phrase,
        "annotator": annotator,
    }


def raw_body(text: str) -> tuple[str, int]:
    start_marker = "<!-- DOCX-BODY-START -->"
    end_marker = "<!-- DOCX-BODY-END -->"
    if start_marker in text and end_marker in text:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        body = text[start:end].strip("\r\n ")
        line_offset = text[:start].count("\n")
        return body, line_offset
    return text, 0


def clean_heading(line: str) -> tuple[str, str | None]:
    value = line.strip()
    value = re.sub(r"^\s*>\s*", "", value)
    value = re.sub(r"^\s*#{1,6}\s*", "", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = value.strip().strip("*").strip()
    value = re.sub(r"^(?:\d+|[一二三四五六七八九十]+)\s*[.．、，,）)]\s*", "", value)
    compact = re.sub(r"\s+", "", value)
    for alias, canonical in sorted(SECTION_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        alias_compact = re.sub(r"\s+", "", alias)
        if compact == alias_compact:
            return canonical, None
        if compact.startswith(alias_compact):
            rest = value[len(alias):].strip()
            if rest.startswith(("：", ":")):
                return canonical, rest[1:].strip()
    # A bare label can have terminal punctuation or a DOCX-style full-width colon.
    trimmed = compact.rstrip("：:。．.")
    for alias, canonical in SECTION_ALIASES.items():
        if trimmed == re.sub(r"\s+", "", alias):
            return canonical, None
    return "", None


def extract_sections(body: str, line_offset: int) -> dict[str, dict[str, Any]]:
    lines = body.splitlines()
    result: dict[str, dict[str, Any]] = {}
    current_label: str | None = None
    current_lines: list[str] = []
    current_start = 0

    def flush(end_line: int) -> None:
        nonlocal current_label, current_lines, current_start
        if current_label is None:
            return
        text = "\n".join(current_lines).strip()
        record = result.setdefault(current_label, {"text": "", "spans": []})
        if record["text"]:
            record["text"] += "\n\n"
        record["text"] += text
        record["spans"].append(
            {
                "line_start": line_offset + current_start,
                "line_end": line_offset + max(current_start, end_line),
                "text": text,
            }
        )
        current_label = None
        current_lines = []

    for index, line in enumerate(lines, start=1):
        label, inline = clean_heading(line)
        if label:
            flush(index - 1)
            current_label = label
            current_start = index
            current_lines = [inline] if inline else []
        elif current_label is not None:
            current_lines.append(line)
    flush(len(lines))
    return result


def section_text(sections: dict[str, dict[str, Any]], name: str) -> str:
    return str(sections.get(name, {}).get("text", "")).strip()


def parse_process(text: str) -> dict[str, str]:
    stages: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        clean = line.strip().lstrip(">- *").strip()
        clean = re.sub(r"^\d+\s*[.、)）]\s*", "", clean)
        found: tuple[str, str] | None = None
        for label, field in PROCESS_LABELS.items():
            match = re.match(rf"^{re.escape(label)}\s*[：:]?\s*(.*)$", clean)
            if match:
                found = (field, match.group(1).strip())
                break
        if found:
            current = found[0]
            if found[1]:
                stages.setdefault(current, []).append(found[1])
            else:
                stages.setdefault(current, [])
        elif current:
            stages.setdefault(current, []).append(line.rstrip())
    return {
        key: "\n".join(value).strip()
        for key, value in stages.items()
        if "\n".join(value).strip()
    }


def infer_relation_type(note: str, category: str = "") -> str:
    text = f"{category} {note}"
    if re.search(r"當作|当作|當為|当为|訛|讹|脱|脫|衍|補|补|校|誤|误", text):
        return "校勘"
    if re.search(r"虛詞|虚词|語詞|语词|發語|发语|助詞|助词|連詞|连词", text):
        return "虚词用法"
    if re.search(r"通假|通用|形近|字形|聲近|声近|聲轉|声转|異體|异体|假借", text):
        return "字际关系"
    if re.search(r"訓|训|猶|犹|義|义|指", text):
        return "训释"
    if re.search(r"句|文義|文义|語境|语境", text):
        return "句义解释"
    return "未定"


def extract_term_relations(
    filename_meta: dict[str, str],
    sections: dict[str, dict[str, Any]],
    claim: str,
    conclusion: str,
) -> tuple[list[dict[str, Any]], bool]:
    source_text = section_text(sections, "term_relations")
    candidate_text = "\n".join(x for x in [source_text, claim, conclusion] if x)
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(left: str, right: str, relation_type: str, note: str, line: str = "") -> None:
        left = left.strip().strip("“”「」『』‘’、，,；;。:： ")
        right = right.strip().strip("“”「」『』‘’、，,；;。:： ")
        if not left or not right or left == right:
            return
        key = (left, right, relation_type)
        if key in seen:
            return
        seen.add(key)
        relations.append(
            {
                "source_term": left,
                "target_term": right,
                "relation_type": relation_type,
                "relation_note": note.strip() or None,
                "_source_line": line,
            }
        )

    for line in candidate_text.splitlines():
        category = line.split("：", 1)[0].split(":", 1)[0].strip()
        relation_type = infer_relation_type(line, category)
        for match in ARROW_CHAIN_RE.finditer(line):
            chain = re.split(r"\s*(?:↔|⇄|→|⇒|＝|=)\s*", match.group(0))
            for left, right in zip(chain, chain[1:]):
                add(left, right, relation_type, line, line)
        for match in QUOTED_RELATION_RE.finditer(line):
            op = match.group(2)
            add(match.group(1), match.group(3), infer_relation_type(op, category), line, line)
        for match in UNQUOTED_RELATION_RE.finditer(line):
            add(
                match.group(1),
                match.group(3),
                infer_relation_type(match.group(2), category),
                line,
                line,
            )
        for match in SOUND_RELATION_RE.finditer(line):
            add(match.group(1), match.group(2), "字际关系", line, line)
        for match in VIRTUAL_GLOSS_RE.finditer(line):
            add(match.group(1), match.group(2), "虚词用法", line, line)
        if not source_text or line in source_text.splitlines():
            match = BARE_RELATION_RE.match(line.strip())
            if match:
                operator = re.search(r"當作|当作|當為|当为|訓為|训为|訓爲|训爲|讀為|读为|讀爲|读爲|通|猶|犹|指|作", line)
                add(
                    match.group(1),
                    match.group(2),
                    infer_relation_type(operator.group(0) if operator else line, category),
                    line,
                    line,
                )

    phrase = filename_meta["case_phrase"]
    if not relations and re.search(r"[犹猶]", phrase):
        left, right = re.split(r"[犹猶]", phrase, maxsplit=1)
        add(left, right, "训释", "由个案文件名中的明确‘犹’关系抽取。", "filename")
    if not relations and re.search(r"發語詞|发语词", phrase):
        root = re.split(r"發語詞|发语词", phrase, maxsplit=1)[0]
        add(root, "发语词", "虚词用法", "由个案文件名中的明确义项抽取。", "filename")

    used_placeholder = not relations
    if used_placeholder:
        relations.append(
            {
                "source_term": phrase or filename_meta["case_id"],
                "target_term": "未抽取",
                "relation_type": "未定",
                "relation_note": "自动转换未能从原文安全抽取词项关系，需人工补录。",
                "_source_line": "placeholder",
            }
        )
    return relations, used_placeholder


def extract_evidence_candidates(
    source_text: str,
    line_offset: int,
    *,
    from_citation_section: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidences: list[dict[str, Any]] = []
    unparsed_lines: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for index, line in enumerate(source_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped in {"<!-- -->", "<!-- DOCX-BODY-START -->", "<!-- DOCX-BODY-END -->"}:
            continue
        matches = list(QUOTE_RE.finditer(line))
        added = False
        for match in matches:
            quote = next((group for group in match.groups() if group is not None), "").strip()
            if not quote:
                continue
            key = (quote, index)
            if key in seen:
                continue
            seen.add(key)
            context = line.strip()
            evidences.append(
                {
                    "quote": quote,
                    "evidence_role": "从标注 Markdown 的引文中自动抽取；底本和版本未核。",
                    "source_work": None,
                    "passage_id": None,
                    "quote_check": "unchecked",
                    "source_resolution": "external_source_pending",
                    "citation_context": context,
                    "_source_line": line_offset + index,
                }
            )
            added = True
        if not added and re.search(r"《[^》]+》|引文|引曰|注曰|云：|曰：", stripped):
            unparsed_lines.append(
                {"line": line_offset + index, "text": stripped}
            )
    return evidences, unparsed_lines


def candidate_phrases(
    meta: dict[str, str], target_text: str, parent_phrase: str | None = None
) -> list[str]:
    values = [meta["case_phrase"], target_text]
    # Multi-quote case titles often abbreviate a canonical entry title. Split
    # only the filename locator; do not split the longer scholarly target text.
    values.extend(re.split(r"[、，,；;]+", meta["case_phrase"]))
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = value.strip().strip("《》【】()（）“”「」『』‘’：:，,。 ")
        normalized = compact_key(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(value)
    return output


def load_canonical_passages(database: Path) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    by_work: dict[str, list[dict[str, Any]]] = {}
    case_ids: set[str] = set()
    uri = f"file:{quote(str(database.resolve()).replace('\\', '/'), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    rows = connection.execute(
        """
        SELECT p.passage_id, p.work_key, p.document_title, p.section_title,
               p.entry_title, p.local_ordinal, p.md_line_start, p.md_line_end,
               p.plain_text, p.normalized_text, s.source_file
        FROM passages p
        JOIN source_documents s ON s.source_document_id = p.source_document_id
        WHERE s.canonical_status = 'canonical_active'
        """
    ).fetchall()
    for row in rows:
        by_work.setdefault(row["work_key"], []).append(dict(row))
    case_ids = {row[0] for row in connection.execute("SELECT case_id FROM annotation_cases")}
    connection.close()
    return by_work, case_ids


def match_source_passage(
    source_work: str,
    phrases: list[str],
    by_work: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    work_key = SOURCE_WORK_KEYS.get(source_work)
    if not work_key:
        return {"status": "unmapped_source_work", "work_key": None, "candidates": []}
    passages = by_work.get(work_key, [])
    scores: dict[str, tuple[int, dict[str, Any], str]] = {}
    for passage in passages:
        title = passage.get("entry_title") or ""
        title_norm = normalize_text(title)
        plain_norm = passage.get("normalized_text") or normalize_text(passage.get("plain_text", ""))
        for phrase in phrases:
            phrase_norm = normalize_text(phrase)
            phrase_key = compact_key(phrase)
            if not phrase_norm:
                continue
            score = 0
            reason = ""
            if title_norm and compact_key(title) == phrase_key:
                score, reason = 4, "exact_entry_title"
            elif (
                len(phrase_key) >= 3
                and len(compact_key(title)) >= 3
                and (phrase_key in compact_key(title) or compact_key(title) in phrase_key)
            ):
                score, reason = 3, "entry_title_contains_phrase"
            elif len(phrase_norm) >= 4 and phrase_norm in plain_norm:
                score, reason = 1, "phrase_in_canonical_passage"
            if score:
                prior = scores.get(passage["passage_id"])
                if prior is None or score > prior[0]:
                    scores[passage["passage_id"]] = (score, passage, reason)
    if not scores:
        return {"status": "no_match", "work_key": work_key, "candidates": []}
    best_score = max(item[0] for item in scores.values())
    best = [item for item in scores.values() if item[0] == best_score]
    summaries = [
        {
            "passage_id": row["passage_id"],
            "entry_title": row.get("entry_title"),
            "section_title": row.get("section_title"),
            "md_line_start": row.get("md_line_start"),
            "md_line_end": row.get("md_line_end"),
            "match_method": reason,
        }
        for _, row, reason in sorted(best, key=lambda item: item[1]["passage_id"])
    ]
    if len(best) == 1:
        _, row, reason = best[0]
        return {
            "status": reason,
            "work_key": work_key,
            "passage_id": row["passage_id"],
            "source_file": row["source_file"],
            "document_title": row.get("document_title"),
            "section_title": row.get("section_title"),
            "entry_title": row.get("entry_title"),
            "md_line_start": row.get("md_line_start"),
            "md_line_end": row.get("md_line_end"),
            "candidates": summaries,
        }
    return {"status": "ambiguous", "work_key": work_key, "candidates": summaries}


def parse_schema_errors(case: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    if JSON_SCHEMA_VALIDATOR is not None:
        validator = JSON_SCHEMA_VALIDATOR(schema)
        return [
            f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in sorted(validator.iter_errors(case), key=lambda error: list(error.absolute_path))
        ]
    errors: list[str] = []
    for name in schema.get("required", []):
        if name not in case:
            errors.append(f"missing required field: {name}")
    if case.get("schema_version") != "annotation_case.v1":
        errors.append("schema_version must be annotation_case.v1")
    for name in ("case_title", "submitted_by", "source_work", "target_text", "conclusion"):
        if not isinstance(case.get(name), str) or not case[name]:
            errors.append(f"{name} must be a non-empty string")
    for name in ("term_relations", "evidences", "target_works"):
        if not isinstance(case.get(name), list):
            errors.append(f"{name} must be an array")
    if isinstance(case.get("term_relations"), list):
        if not case["term_relations"]:
            errors.append("term_relations must contain at least one item")
        for index, relation in enumerate(case["term_relations"]):
            if not isinstance(relation, dict):
                errors.append(f"term_relations[{index}] must be an object")
                continue
            for field in ("source_term", "target_term"):
                if not isinstance(relation.get(field), str) or not relation[field]:
                    errors.append(f"term_relations[{index}].{field} must be non-empty")
            relation_type = relation.get("relation_type")
            if relation_type not in {"训释", "校勘", "字际关系", "虚词用法", "句义解释", "未定", None}:
                errors.append(f"term_relations[{index}].relation_type is invalid")
    if isinstance(case.get("evidences"), list):
        for index, evidence in enumerate(case["evidences"]):
            if not isinstance(evidence, dict) or not isinstance(evidence.get("quote"), str) or not evidence.get("quote"):
                errors.append(f"evidences[{index}].quote must be a non-empty string")
                continue
            if evidence.get("quote_check") not in {"unchecked", "passed", "failed", "normalized_passed", None}:
                errors.append(f"evidences[{index}].quote_check is invalid")
    if case.get("machine_result", {}).get("status") not in {"pending", "draft", "approved", "rejected"}:
        errors.append("machine_result.status is invalid")
    if case.get("human_review", {}).get("status") not in {"pending", "approved", "rejected", "uncertain"}:
        errors.append("human_review.status is invalid")
    return errors


def build_record(
    path: Path,
    source_dir: Path,
    archive_dir: Path,
    by_work: dict[str, list[dict[str, Any]]],
    existing_case_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_bytes = path.read_bytes()
    raw_text = raw_bytes.decode("utf-8-sig")
    meta = parse_filename(path)
    body, line_offset = raw_body(raw_text)
    sections = extract_sections(body, line_offset)
    section_values = {name: item["text"] for name, item in sections.items()}
    process_text = section_text(sections, "process_text")
    process = parse_process(process_text)

    target_text = section_text(sections, "target_text")
    target_text_source = "explicit_section"
    phrase = meta["case_phrase"]
    if not target_text:
        if meta["source_work"] == "广雅疏证" and meta["target_label"] == "广雅":
            first_entry = re.search(
                r"(?m)^([^\n。]*?(?:始也|敬也|創也)[。]?)$", body
            )
            target_text = first_entry.group(1).strip() if first_entry else phrase
            target_text_source = "source_entry_line" if first_entry else "filename"
        elif meta["source_work"] == "经传释词" and re.match(r"\d{3}[A-Z]", meta["case_id"]):
            target_text = re.split(r"犹|猶|發語詞|发语词", phrase, maxsplit=1)[0].strip()
            target_text_source = "split_case_title"
        else:
            target_text = phrase
            target_text_source = "filename"
    target_text = target_text.strip()

    claim = section_text(sections, "claim")
    conclusion = section_text(sections, "conclusion")
    conclusion_source = "explicit_section" if conclusion else ""
    if not conclusion:
        conclusion = process.get("conclusion", "")
        if conclusion:
            conclusion_source = "process_conclusion"
    if not conclusion:
        conclusion = claim or section_text(sections, "overall_summary") or section_text(sections, "lexical_items")
        if conclusion:
            conclusion_source = "claim_or_summary_fallback"
    conclusion_placeholder = not bool(conclusion.strip())
    if conclusion_placeholder:
        conclusion = "未抽取，需人工补录。"
        conclusion_source = "placeholder"

    source_argument = section_text(sections, "source_argument")
    evidence_source = section_text(sections, "evidence_text")
    evidence_from_body = False
    evidence_line_offset = line_offset
    if not evidence_source:
        evidence_source = source_argument or body
        evidence_from_body = True
        if source_argument and sections.get("source_argument", {}).get("spans"):
            evidence_line_offset = sections["source_argument"]["spans"][0]["line_start"]
    elif sections.get("evidence_text", {}).get("spans"):
        evidence_line_offset = sections["evidence_text"]["spans"][0]["line_start"]
    evidences, unparsed_evidence_lines = extract_evidence_candidates(
        evidence_source,
        evidence_line_offset,
        from_citation_section=not evidence_from_body,
    )

    term_relations, term_placeholder = extract_term_relations(
        meta, sections, claim, conclusion
    )
    target_label = meta["target_label"]
    if target_label in {"诸书", "諸書"}:
        target_work = ""
        target_works: list[str] = []
        target_scope = {"status": "unknown", "raw_label": target_label}
    else:
        target_work = target_label
        target_works = [target_label]
        target_scope = {"status": "candidate_only", "raw_label": target_label}

    source_id = meta["source_id"]
    archive_matches = sorted(archive_dir.glob(f"{source_id}-*.md"))
    archive_path = archive_matches[0] if len(archive_matches) == 1 else None
    archive_bytes = archive_path.read_bytes() if archive_path else None
    parent_phrase = parse_filename(archive_path)["case_phrase"] if archive_path else None
    case_id = f"manual_md:{meta['case_id']}"
    phrases = candidate_phrases(meta, target_text, parent_phrase)
    source_match = match_source_passage(meta["source_work"], phrases, by_work)
    # A split note can address one word inside a parent entry title. Only use
    # that parent title when the explicit target text is literally contained
    # in it; this avoids matching sibling cases from a parent file name.
    target_key = compact_key(target_text)
    parent_key = compact_key(parent_phrase or "")
    if (
        source_match.get("status") == "no_match"
        and target_key
        and parent_key
        and target_key in parent_key
    ):
        parent_match = match_source_passage(meta["source_work"], [parent_phrase], by_work)
        if parent_match.get("passage_id"):
            parent_match["status"] = "parent_entry_context_match"
            parent_match["direct_target_status"] = source_match.get("status")
            source_match = parent_match
            phrases.append(parent_phrase)
    source_passage_id = source_match.get("passage_id")
    source_location = None
    if source_passage_id:
        source_location = {
            "source_file": source_match.get("source_file"),
            "document_title": source_match.get("document_title"),
            "section_title": source_match.get("section_title"),
            "entry_title": source_match.get("entry_title"),
            "md_line_start": source_match.get("md_line_start"),
            "md_line_end": source_match.get("md_line_end"),
            "match_method": source_match.get("status"),
        }
    relative_source = path.resolve().relative_to(ROOT).as_posix()
    relative_archive = archive_path.resolve().relative_to(ROOT).as_posix() if archive_path else None
    word_comment_count = len(re.findall(r"(?m)^###\s*批注\s*\d+", raw_text))

    migration = {
        "source_layer": "manual_annotation_markdown",
        "transformation_kind": "deterministic_markdown_to_annotation_case_v1_candidate",
        "source_file": relative_source,
        "source_sha256": sha256_bytes(raw_bytes),
        "source_id": meta["case_id"],
        "parent_source_id": source_id,
        "archive_markdown_file": relative_archive,
        "archive_markdown_sha256": sha256_bytes(archive_bytes) if archive_bytes is not None else None,
        "archive_markdown_match_status": (
            "same_file_content" if archive_bytes == raw_bytes else "split_from_archive_source" if archive_bytes else "missing_or_ambiguous"
        ),
        "annotator_from_filename": meta["annotator"],
        "target_label_from_filename": target_label,
        "target_text_extraction": target_text_source,
        "conclusion_extraction": conclusion_source,
        "source_passage_match": source_match,
        "source_phrases_searched": phrases,
        "word_comments_count": word_comment_count,
        "source_sections": section_values,
        "source_section_spans": {name: item["spans"] for name, item in sections.items()},
        "raw_markdown": raw_text,
        "conversion_flags": [],
    }
    flags: list[str] = []
    if target_text_source != "explicit_section":
        flags.append(f"target_text_from_{target_text_source}")
    if conclusion_placeholder:
        flags.append("conclusion_placeholder")
    if term_placeholder:
        flags.append("term_relation_placeholder")
    if not evidences:
        flags.append("no_structured_evidence_quotes")
    if evidences:
        flags.append("evidence_quotes_unlinked_and_unverified")
    if source_match.get("status") not in {
        "exact_entry_title",
        "entry_title_contains_phrase",
        "phrase_in_canonical_passage",
        "parent_entry_context_match",
    }:
        flags.append(f"source_passage_{source_match.get('status')}")
    if target_scope["status"] != "resolved":
        flags.append(f"target_work_{target_scope['status']}")
    if case_id in existing_case_ids:
        flags.append("case_id_collision_existing_database_record")
    migration["conversion_flags"] = flags

    case: dict[str, Any] = {
        "schema_version": "annotation_case.v1",
        "case_id": case_id,
        "case_title": phrase or meta["case_id"],
        "submitted_by": meta["annotator"],
        "reviewed_by": None,
        "source_work": meta["source_work"],
        "source_passage_id": source_passage_id,
        "source_location": source_location,
        "target_work": target_work,
        "target_works": target_works,
        "target_scope": target_scope,
        "target_text": target_text,
        "target_passage_id": None,
        "target_location": None,
        "term_relations": term_relations,
        "evidences": evidences,
        "evidence_state": "present",
        "problem_discovery": process.get("problem_discovery"),
        "research_question": process.get("research_question"),
        "evidence_collection": process.get("evidence_collection"),
        "reasoning": process.get("reasoning"),
        "conclusion": conclusion,
        "method_profile": {
            "raw_terms": section_text(sections, "method_terms") or None,
            "claim_text": claim or None,
        },
        "machine_result": {
            "status": "draft",
            "method": "deterministic_markdown_parser",
            "schema_checked": False,
        },
        "human_review": {"status": "pending"},
        "_migration": migration,
    }

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_errors = parse_schema_errors(case, schema)
    try:
        from erwang_v2.validate_annotation_case import validate_case, classify_machine_status

        canonical_passages = {
            passage["passage_id"]: {"plain_text": passage["plain_text"]}
            for passages in by_work.values()
            for passage in passages
        }
        semantic_errors = validate_case(case, canonical_passages)
        classification = classify_machine_status(semantic_errors, schema_errors)
    except Exception as exc:
        semantic_errors = [f"validator_unavailable:{type(exc).__name__}:{exc}"]
        classification = "not_checked"
    case["machine_result"]["schema_checked"] = not bool(schema_errors)
    case["machine_result"]["classification"] = classification

    blockers = list(flags)
    if schema_errors:
        blockers.append("json_schema_invalid")
    if unparsed_evidence_lines:
        blockers.append("evidence_lines_need_review")
    if source_match.get("status") == "ambiguous":
        blockers.append("source_passage_ambiguous")
    collision = case_id in existing_case_ids
    draft_ingest_candidate = (
        not schema_errors
        and not collision
        and source_match.get("status") in {
            "exact_entry_title",
            "entry_title_contains_phrase",
            "phrase_in_canonical_passage",
            "parent_entry_context_match",
        }
    )
    case_report = {
        "case_id": meta["case_id"],
        "database_case_id": case_id,
        "source_file": relative_source,
        "archive_markdown_file": relative_archive,
        "source_sha256": migration["source_sha256"],
        "annotator": meta["annotator"],
        "source_work": meta["source_work"],
        "target_work_raw_label": target_label,
        "target_text_source": target_text_source,
        "source_passage_match": source_match,
        "term_relation_count": len(term_relations),
        "term_relation_placeholder": term_placeholder,
        "evidence_quote_count": len(evidences),
        "unparsed_evidence_line_count": len(unparsed_evidence_lines),
        "word_comments_count": word_comment_count,
        "process_fields_missing": [
            field
            for field in (
                "problem_discovery",
                "research_question",
                "evidence_collection",
                "reasoning",
            )
            if not case.get(field)
        ],
        "schema_valid": not bool(schema_errors),
        "schema_errors": schema_errors,
        "semantic_validation_errors": semantic_errors,
        "machine_classification": classification,
        "case_id_collision": collision,
        "draft_ingest_candidate": draft_ingest_candidate,
        "approval_ready": False,
        "blockers": sorted(set(blockers)),
        "unparsed_evidence_lines": unparsed_evidence_lines,
    }
    return case, case_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--archive-dir", type=Path, default=None)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    archive_dir = (args.archive_dir or source_dir.parent / "archive" / "md").resolve()
    database = args.database.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = sorted(path for path in source_dir.glob("*.md") if path.name != "README.md")
    readme_path = source_dir / "README.md"
    if not readme_path.is_file():
        raise SystemExit(f"case mapping README is missing: {readme_path}")
    expected_cases = sum(
        1
        for line in readme_path.read_text(encoding="utf-8-sig").splitlines()
        if re.match(r"^\|\s*\d{3}\s*\|\s*\d{3}[A-Z]?\s*\|", line)
    )
    if len(inputs) != expected_cases:
        raise SystemExit(
            f"README maps {expected_cases} case files in {source_dir}, found {len(inputs)} Markdown files"
        )

    sys.path.insert(0, str(V2_ROOT / "src"))
    if database.is_file():
        by_work, existing_case_ids = load_canonical_passages(database)
        db_status = "opened_read_only"
    else:
        by_work, existing_case_ids = {}, set()
        db_status = "database_not_found_source_matching_skipped"

    cases: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for path in inputs:
        case, case_report = build_record(
            path,
            source_dir,
            archive_dir,
            by_work,
            existing_case_ids,
        )
        cases.append(case)
        reports.append(case_report)

    jsonl_path = output_dir / "manual_annotation_cases.annotation_case.v1.candidates.jsonl"
    report_path = output_dir / "manual_annotation_conversion_report.json"
    jsonl_path.write_text(
        "".join(json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for case in cases),
        encoding="utf-8",
        newline="\n",
    )
    blocker_counts = Counter(flag for report in reports for flag in report["blockers"])
    summary = {
        "converter_version": "1.0.0",
        "schema_version": "annotation_case.v1",
        "schema_validation_method": SCHEMA_VALIDATION_METHOD,
        "input_directory": source_dir.relative_to(ROOT).as_posix(),
        "archive_directory": archive_dir.relative_to(ROOT).as_posix(),
        "database_path": database.relative_to(ROOT).as_posix(),
        "database_access": db_status,
        "database_writes_performed": False,
        "case_count": len(cases),
        "jsonl_path": jsonl_path.relative_to(ROOT).as_posix(),
        "report_path": report_path.relative_to(ROOT).as_posix(),
        "summary": {
            "schema_valid_cases": sum(report["schema_valid"] for report in reports),
            "source_passage_matched_cases": sum(bool(report["source_passage_match"].get("passage_id")) for report in reports),
            "source_passage_ambiguous_cases": sum(report["source_passage_match"].get("status") == "ambiguous" for report in reports),
            "term_relation_placeholder_cases": sum(report["term_relation_placeholder"] for report in reports),
            "cases_with_evidence_quotes": sum(report["evidence_quote_count"] > 0 for report in reports),
            "all_evidence_quotes_unverified": sum(report["evidence_quote_count"] for report in reports),
            "cases_with_unparsed_evidence_lines": sum(report["unparsed_evidence_line_count"] > 0 for report in reports),
            "word_comment_count": sum(report["word_comments_count"] for report in reports),
            "existing_case_id_collisions": sum(report["case_id_collision"] for report in reports),
            "draft_ingest_candidates": sum(report["draft_ingest_candidate"] for report in reports),
            "approval_ready_cases": 0,
            "blocker_counts": dict(sorted(blocker_counts.items())),
        },
        "cases": reports,
    }
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary["summary"], ensure_ascii=False, indent=2))
    print(f"JSONL: {jsonl_path}")
    print(f"Report: {report_path}")
    print("Database writes: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Import cases from the reviewed Markdown sources into annotations.db.

This importer is deliberately separate from the DOCX/DeepSeek pipeline.  It
only accepts the ten reviewed Markdown templates, requires the two local
cross-review reports, skips the four cases already present in annotations.db,
and writes the ten new cases as 草稿/待核 records.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = ROOT / "04-项目文献" / "0-当前阅读" / "archive" / "md"
DB_PATH = ROOT / "02-数据库" / "data" / "annotations.db"
TMP_DIR = ROOT / "tmp"
REPORT_PATH = TMP_DIR / "manual_markdown_ingest_report.json"
REVIEW_A = TMP_DIR / "manual_ingest_review_A.md"
REVIEW_B = TMP_DIR / "manual_ingest_review_B.md"
REVIEW_A_004 = TMP_DIR / "manual_ingest_review_A_004_resolution.md"
REVIEW_B_004 = TMP_DIR / "manual_ingest_review_B_004_resolution.md"


SECTION_ALIASES = {
    "考據對象": "考据对象",
    "考据对象": "考据对象",
    "反駁對象": "反驳对象",
    "反驳对象": "反驳对象",
    "論點": "论点",
    "论点": "论点",
    "字詞關係": "字词关系",
    "字词关系": "字词关系",
    "引用書證": "引用书证",
    "引用书证": "引用书证",
    "運用術語": "考据用语",
    "运用术语": "考据用语",
    "考據用語": "考据用语",
    "考据用语": "考据用语",
    "考據過程": "考据过程",
    "考据过程": "考据过程",
}

METHOD_TAGS = {
    "校勘",
    "训释",
    "声训",
    "通假",
    "异体",
    "异文",
    "同义互证",
    "义证",
    "书证",
    "形证",
    "语法证据",
    "对文散文",
    "句义解释",
    "补正",
}


@dataclass
class CaseSpec:
    key: str
    source_file: str
    case_title: str
    source_work: str
    target_work: str
    target_text: str
    problem: str
    claim: str
    conclusion: str
    method_tags: list[str]
    mode: str = "numbered"
    block_index: int = 0
    terms: list[dict[str, str]] = field(default_factory=list)
    evidence_quotes: list[dict[str, str]] = field(default_factory=list)
    process_steps: list[dict[str, str]] = field(default_factory=list)
    raw_line_start: int | None = None
    raw_line_end: int | None = None
    uncertainties: list[str] = field(default_factory=list)


def _term(term: str, related: str = "", relation: str = "", note: str = "") -> dict[str, str]:
    return {
        "term": term,
        "term_type": "字词",
        "relation_type": relation,
        "related_term": related,
        "note": note or relation,
    }


def _evidence(quote: str, work: str = "", role: str = "书证") -> dict[str, str]:
    return {"evidence_type": "书证", "work": work, "quote": quote, "role": role, "term": ""}


def _step(step_type: str, text: str, mapping_status: str = "source_labeled") -> dict[str, str]:
    return {"step_type": step_type, "text": text, "mapping_status": mapping_status}


def _clean_heading(line: str) -> str:
    text = re.sub(r"^\s*[>*#\d一二三四五六七八九十]+[.、，,：:\s]*", "", line)
    text = text.replace("**", "").strip()
    return text


def _section_label(line: str) -> str | None:
    cleaned = _clean_heading(line)
    for raw, normalized in sorted(SECTION_ALIASES.items(), key=lambda x: -len(x[0])):
        if cleaned == raw or cleaned.startswith(raw + " ") or cleaned.startswith(raw + "："):
            return normalized
    return None


def _numbered_blocks(lines: list[str]) -> list[dict[str, Any]]:
    starts = [i for i, line in enumerate(lines) if _section_label(line) == "考据对象"]
    blocks: list[dict[str, Any]] = []
    for block_index, start in enumerate(starts):
        end = starts[block_index + 1] if block_index + 1 < len(starts) else len(lines)
        sections: dict[str, list[str]] = {}
        section_lines: dict[str, tuple[int, int]] = {}
        current: str | None = None
        current_start = start
        for index in range(start, end):
            label = _section_label(lines[index])
            if label:
                if current is not None:
                    sections[current] = lines[current_start + 1 : index]
                    section_lines[current] = (current_start + 1, index)
                current = label
                current_start = index
        if current is not None:
            sections[current] = lines[current_start + 1 : end]
            section_lines[current] = (current_start + 1, end)
        blocks.append({"start": start + 1, "end": end, "sections": sections, "section_lines": section_lines})
    return blocks


def _nonblank(lines: Iterable[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def _join(lines: Iterable[str]) -> str:
    return "\n".join(_nonblank(lines))


def _parse_relation(line: str) -> dict[str, str]:
    raw = line.strip().strip("-•")
    normalized = raw.replace("“", "").replace("”", "").replace("‘", "").replace("’", "")
    relation = ""
    if "通假" in normalized or "通" in normalized:
        relation = "通假"
    elif "异文" in normalized or "通用" in normalized:
        relation = "异文"
    elif "异体" in normalized:
        relation = "异体"
    elif "声近" in normalized or "一聲之轉" in normalized:
        relation = "声训"
    elif "同义" in normalized or "義" in normalized:
        relation = "同义互证"
    elif "误" in normalized or "譌" in normalized or "脱" in normalized:
        relation = "校勘"
    parts = re.split(r"↔|與|与|和|及|、", normalized, maxsplit=1)
    term = parts[0].strip(" ：:，,；;")
    related = parts[1].strip(" ：:，,；;") if len(parts) > 1 else ""
    return _term(term, related, relation, raw)


def _parse_evidence_lines(lines: Iterable[str]) -> list[dict[str, str]]:
    evidences: list[dict[str, str]] = []
    for raw in _nonblank(lines):
        if raw.startswith(("①", "②", "③", "（", "(", "类别", "顺序", "頻率", "频率")):
            continue
        work_match = re.search(r"《([^》]+)》", raw)
        work = work_match.group(1) if work_match else ""
        quote = raw
        if "：" in raw:
            quote = raw.split("：", 1)[1].strip()
        elif ":" in raw:
            quote = raw.split(":", 1)[1].strip()
        evidences.append(_evidence(quote, work, "书证"))
    return evidences


def _parse_process(lines: Iterable[str]) -> list[dict[str, str]]:
    labels = {"发疑", "發疑", "预设", "預設", "取证", "取證", "释理", "釋理", "结论", "結論"}
    steps: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^([^：:]+)[：:](.*)$", line)
        label = match.group(1).strip() if match else ""
        text = match.group(2).strip() if match else line
        if label in labels:
            mapped = {"發疑": "发疑", "預設": "立论", "取證": "取证", "釋理": "释理", "結論": "结论"}.get(label, label)
            current = _step(mapped, text)
            steps.append(current)
        elif current is not None:
            current["text"] = (current["text"] + "\n" + line).strip()
        else:
            steps.append(_step("释理", line, "section_inferred"))
    return steps


def _find_conclusion(lines: list[str], fallback: str) -> str:
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:结论|結論)\s*[：:]?\s*(.*)$", line)
        if match:
            text = match.group(1).strip()
            following: list[str] = []
            for next_line in lines[index + 1 :]:
                if _section_label(next_line) or re.match(r"^\s*#{1,6}\s", next_line):
                    break
                if next_line.strip():
                    following.append(next_line.strip())
            value = "\n".join([part for part in [text, *following] if part])
            return value.replace("<!-- DOCX-BODY-END -->", "").strip()
    return fallback.replace("<!-- DOCX-BODY-END -->", "").strip()


def _body_text(lines: list[str]) -> str:
    try:
        start = lines.index("<!-- DOCX-BODY-START -->") + 1
    except ValueError:
        start = 0
    try:
        end = lines.index("<!-- DOCX-BODY-END -->")
    except ValueError:
        end = len(lines)
    return "\n".join(lines[start:end]).strip()


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def _manual_case_specs() -> list[CaseSpec]:
    return [
        CaseSpec(
            "003-始也",
            "003-广雅疏证-广雅-始也-华建光.md",
            "始也",
            "广雅疏证",
            "广雅",
            "古、昔、先、創、方、作、造、朔、萌、芽、本、根、櫱、鼃、戶瓜反 䔞、律 昌、孟、鼻、業，始也。",
            "正文称此条列出约二十字且部分字无疏证，律为王念孙校补；具体字表和校补边界需保留待核。",
            "条首所列字词训为始也，并以逐字书证、通假、声训和同义关系说明可释者。",
            "条目以始也为总训；律为王念孙校补，补正材料为《莊子·秋水篇》句。",
            ["训释", "书证", "通假", "声训", "同义互证", "补正", "校勘"],
            mode="始也",
            terms=[
                _term("作", "乍", "声训", "作之言乍也"),
                _term("作", "乃", "句义解释", "与乃相对成文"),
                _term("作", "既", "句义解释", "与既相对成文"),
                _term("櫱", "萌芽", "同义互证", "櫱与萌芽同义"),
                _term("律", "䔞", "通假", "律与䔞通"),
                _term("䔞", "聿", "声训", "声与䔞近而义同"),
                _term("昌", "倡", "通假", "昌读为倡"),
                _term("鼻", "自", "声训", "鼻之言自也"),
                _term("業", "基", "同义互证", "業与基同义"),
            ],
            uncertainties=["正文说20字，批注说19字；前若干字、孟等明确无疏证；律为校补。"],
        ),
        CaseSpec(
            "004-允-用",
            "004-经传释词-诸书-允-徐健怡.md",
            "允，猶「用」也",
            "经传释词",
            "诸书",
            "允",
            "诸书旧注多训允为信，王氏认为列举用例中文义未安。",
            "允犹用，为语词。",
            "允在所列用例中可作语词用解；旧训允信与相应用例文义不合。",
            ["训释", "书证", "句义解释", "对文散文"],
            mode="允-用",
            terms=[_term("允", "用", "同义互证", "允犹用"), _term("允", "信", "校勘", "旧训信被反驳"), _term("允", "語詞", "句义解释", "允为语词")],
            evidence_quotes=[
                _evidence("允釐百工；允迪厥德；庶尹允諧；允蠢鰥寡；允執其中；允出兹在兹；懷允不忘；豳居允荒；允臻其極；允懷多福。", "诸书", "义项①书证汇总"),
            ],
            process_steps=[
                _step("发疑", "诸书旧注以允为信，部分用例文义未安。", "agent_consensus_inferred"),
                _step("取证", "逐列《尚书》《左传》《论语》《诗经》《考工记》等用例并与语词用法对读。", "agent_consensus_inferred"),
                _step("释理", "允在这些句中承接文句，不取实信义；旧注与文义不合。", "agent_consensus_inferred"),
                _step("结论", "允犹用，为语词。", "source_heading"),
            ],
            uncertainties=["target_work为多部书范围，不代表单一典籍；证据汇总保留在raw_case_json。"],
        ),
        CaseSpec(
            "004-允-以",
            "004-经传释词-诸书-允-徐健怡.md",
            "允，猶「以」也",
            "经传释词",
            "诸书",
            "允",
            "允与用、以的义项关系需要由《墨子》引《商书》和声义关系说明。",
            "允犹以，表连及、并列，可译为以及。",
            "允可训为以；以与用同义。",
            ["训释", "书证", "声训", "同义互证"],
            mode="允-以",
            terms=[_term("允", "以", "同义互证", "允犹以"), _term("以", "用", "同义互证", "以与用同义"), _term("允", "用", "声训", "一聲之轉")],
            evidence_quotes=[
                _evidence("百獸貞蟲，允及飛鳥，莫不比方。", "墨子·明鬼篇引商書", "义项②书证"),
                _evidence("允，從儿，聲。", "說文", "字书证据"),
            ],
            process_steps=[
                _step("立论", "允犹以。", "source_heading"),
                _step("取证", "以《墨子·明鬼篇》引《商書》用例说明允及飞鸟。", "agent_consensus_inferred"),
                _step("释理", "允与以、用在声义关系上相通。", "agent_consensus_inferred"),
                _step("结论", "允犹以，表连及、并列。", "source_heading"),
            ],
            uncertainties=["正文含字形缺失的异体显示，原始全文保留。"],
        ),
        CaseSpec(
            "004-允-發語詞",
            "004-经传释词-诸书-允-徐健怡.md",
            "允，發語詞也",
            "经传释词",
            "诸书",
            "允",
            "诗句句首允是否为实义信还是发语词。",
            "允为发语词/语词，无实义；允文与於皇对文。",
            "允在时迈、武、泮水等句中为发语词，旧笺训信失之。",
            ["训释", "书证", "句义解释", "对文散文"],
            mode="允-發語詞",
            terms=[_term("允", "發語詞", "句义解释", "句首发端语气虚词"), _term("允文", "於皇", "句义解释", "对文"), _term("允", "語詞", "同义互证", "允为语词")],
            evidence_quotes=[
                _evidence("允王維后；允王保之。", "詩·時邁", "义项③书证"),
                _evidence("於皇武王，無競維烈。允文文王，克開厥後。", "詩·武", "对文书证"),
                _evidence("允文允武。", "詩·泮水", "诗句书证"),
                _evidence("乃神乃武乃文。", "吕氏春秋·谕大篇", "旁证"),
            ],
            process_steps=[
                _step("立论", "允为发语词。", "source_heading"),
                _step("取证", "列《時邁》《武》《泮水》诗句及《吕氏春秋》对照。", "agent_consensus_inferred"),
                _step("释理", "允文与於皇对文，句首允无实义。", "agent_consensus_inferred"),
                _step("结论", "允为发语词，旧笺训信失之。", "source_heading"),
            ],
            uncertainties=["target_work为多部书范围，不代表单一典籍。"],
        ),
        CaseSpec(
            "005-終風且暴",
            "005-经义述闻-诗经-終風且暴-李汶灿.md",
            "終風且暴",
            "经义述闻",
            "诗经",
            "終風且暴",
            "毛诗训终日风、韩诗训西风，均为缘词生训而非经文本义。",
            "终犹既也，言既风且暴也。",
            "既与终为语之转；旧解失之。",
            ["训释", "书证", "句义解释", "同义互证"],
            uncertainties=["模板编号把引用书证和字词关系重复编号，按字段语义导入。"],
        ),
        CaseSpec(
            "006-薄言有之",
            "006-经义述闻-诗经-薄言有之-李汶灿.md",
            "薄言有之",
            "经义述闻",
            "诗经",
            "采采芣苡，薄言有之",
            "毛传训有为藏之，与后续掇之、捋之的次序不合。",
            "诗之用词不嫌复；有亦取也。",
            "有亦取；毛传训藏之则不合全篇次序。",
            ["训释", "书证", "句义解释", "同义互证"],
        ),
        CaseSpec(
            "007-伐其條枚",
            "007-经义述闻-诗经-伐其條枚、條肄-李汶灿.md",
            "伐其條枚、伐其條肄、施于條枚",
            "经义述闻",
            "诗经",
            "《汝墳篇》伐其條枚、伐其條肄；《旱麓》施于條枚",
            "毛传、正义及郑笺把條枚解释为枝干/枝本，与《終南》有條有梅及全诗例不合。",
            "当训为有條有梅之條，谓伐其條树之枚、之肄；施于條枚亦实指所依之树。",
            "皆实指其所依之树，不得如笺所云。",
            ["训释", "书证", "句义解释", "同义互证"],
            uncertainties=["对象跨汝墳与旱麓；两 agent 同意暂按一个连接论证 case 保存。"],
        ),
        CaseSpec(
            "008-翹翹錯薪",
            "008-经义述闻-诗经-翹翹錯薪-李汶灿.md",
            "翹翹錯薪，言刈其楚",
            "经义述闻",
            "诗经",
            "翹翹錯薪，言刈其楚",
            "传、笺训翘翘为高，与下句相复。",
            "翘翘与错薪连文，为众多之貌。",
            "翘翘为众多之貌；旧训高则与下句相复。",
            ["训释", "书证", "句义解释", "同义互证"],
        ),
        CaseSpec(
            "009-長幼成而生",
            "009-读书杂志-逸周书-長幼成而生，曰順極-李汶灿.md",
            "長幼成而生，曰順極",
            "读书杂志",
            "逸周书",
            "長幼成而生，曰順極",
            "生字下无所承，文义未完，疑有脱文。",
            "当作長幼成而生義，曰順極，今本盖脱義字。",
            "孔注生其義、順之至分别与正文相应，今本脱義。",
            ["校勘", "书证", "句义解释", "补正"],
        ),
        CaseSpec(
            "010-賞多則乏",
            "010-读书杂志-逸周书-賞多則乏-李汶灿.md",
            "賞多則乏",
            "读书杂志",
            "逸周书",
            "罰多則困，賞多則乏中的賞多則乏",
            "赏多则乏与上文罚多赏少、政之恶也义不相应。",
            "赏多则乏当为赏少则乏。",
            "多字涉上句罚多而误；困、乏皆就民而言。",
            ["校勘", "书证", "句义解释", "义证"],
        ),
    ]


def _review_requirements() -> None:
    required = [REVIEW_A, REVIEW_B, REVIEW_A_004, REVIEW_B_004]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("missing_cross_review_reports:" + ",".join(missing))
    a = REVIEW_A.read_text(encoding="utf-8")
    b = REVIEW_B.read_text(encoding="utf-8")
    for marker in ["### 003：始也", "### 005：終風且暴", "### 006：薄言有之", "### 007：", "### 008：", "### 009：", "### 010："]:
        if marker not in a or marker not in b:
            raise RuntimeError(f"cross_review_marker_missing:{marker}")
    for path in [REVIEW_A_004, REVIEW_B_004]:
        if not re.search(r"拆[成為为] 3", path.read_text(encoding="utf-8")):
            raise RuntimeError(f"004_resolution_not_consensus:{path}")


def _parse_case(spec: CaseSpec) -> dict[str, Any]:
    path = TEMPLATE_DIR / spec.source_file
    if not path.is_file():
        raise FileNotFoundError(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    body = _body_text(lines)
    parsed = copy.deepcopy(spec.__dict__)
    parsed["source_path"] = str(path.relative_to(ROOT)).replace("\\", "/")
    parsed["source_line_count"] = len(lines)
    parsed["source_line_start"] = spec.raw_line_start or 1
    parsed["source_line_end"] = spec.raw_line_end or len(lines)
    parsed["raw_markdown"] = body

    if spec.mode == "numbered":
        blocks = _numbered_blocks(lines)
        if spec.block_index >= len(blocks):
            raise RuntimeError(f"numbered_block_missing:{spec.key}")
        block = blocks[spec.block_index]
        sections = block["sections"]
        parsed["source_line_start"] = block["start"]
        parsed["source_line_end"] = block["end"]
        parsed["raw_case_text"] = "\n".join(lines[block["start"] - 1 : block["end"]]).strip()
        parsed["terms"] = [_parse_relation(line) for line in _nonblank(sections.get("字词关系", []))]
        parsed["evidence_quotes"] = _parse_evidence_lines(sections.get("引用书证", []))
        parsed["process_steps"] = _parse_process(sections.get("考据过程", []))
        parsed["problem"] = _join(sections.get("反驳对象", [])) or spec.problem
        parsed["claim"] = _join(sections.get("论点", [])) or spec.claim
        parsed["target_text"] = _join(sections.get("考据对象", [])) or spec.target_text
        parsed["conclusion"] = _find_conclusion(lines[block["start"] - 1 : block["end"]], spec.conclusion)
        raw_methods = _nonblank(sections.get("考据用语", []))
        parsed["method_tags"] = sorted(set(spec.method_tags + [tag for tag in METHOD_TAGS if any(tag in raw for raw in raw_methods)]))
    elif spec.mode == "始也":
        paragraphs = _paragraphs(body)
        parsed["raw_case_text"] = body
        parsed["evidence_quotes"] = [
            _evidence(paragraph, re.search(r"《([^》]+)》", paragraph).group(1) if re.search(r"《([^》]+)》", paragraph) else "", "原文书证")
            for paragraph in paragraphs
            if "《" in paragraph
        ]
        parsed["process_steps"] = [_step("释词", paragraph, "section_inferred") for paragraph in paragraphs[2:] if paragraph]
    else:
        parsed["raw_case_text"] = body

    return parsed


def _normalize_term_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in case.get("terms", []):
        row = dict(item)
        row.setdefault("source_paragraph_indexes", [])
        row.setdefault("source_comment_ids", [])
        rows.append(row)
    return rows


def _normalize_evidence_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in case.get("evidence_quotes", []):
        row = dict(item)
        row.setdefault("evidence_type", "书证")
        row.setdefault("work", "")
        row.setdefault("quote", "")
        row.setdefault("role", "书证")
        row.setdefault("term", "")
        row.setdefault("source_paragraph_indexes", [])
        row.setdefault("source_comment_ids", [])
        rows.append(row)
    return rows


def _normalize_step_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in case.get("process_steps", []):
        row = dict(item)
        row.setdefault("step_type", "释理")
        row.setdefault("text", "")
        row.setdefault("source_paragraph_indexes", [])
        row.setdefault("source_comment_ids", [])
        rows.append(row)
    return rows


def build_manifest() -> dict[str, Any]:
    _review_requirements()
    cases = [_parse_case(spec) for spec in _manual_case_specs()]
    duplicate_map = {
        "001-平原之隰": {"existing_id": 1, "reason": "same case already in annotations.db"},
        "001-譕臣": {"existing_id": 2, "reason": "same case already in annotations.db"},
        "002-敬也": {"existing_id": 16, "reason": "same case already in annotations.db"},
        "002-創也": {"existing_id": 17, "reason": "same case already in annotations.db"},
    }
    return {
        "manifest_version": "manual_markdown_ingest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_directory": str(TEMPLATE_DIR.relative_to(ROOT)).replace("\\", "/"),
        "reviewers": [
            {"name": "Agent A", "report": str(REVIEW_A.relative_to(ROOT)).replace("\\", "/")},
            {"name": "Agent B", "report": str(REVIEW_B.relative_to(ROOT)).replace("\\", "/")},
            {"name": "Agent A", "report": str(REVIEW_A_004.relative_to(ROOT)).replace("\\", "/")},
            {"name": "Agent B", "report": str(REVIEW_B_004.relative_to(ROOT)).replace("\\", "/")},
        ],
        "duplicate_cases_skipped": duplicate_map,
        "cases": cases,
    }


def _load_existing_cases(conn: sqlite3.Connection) -> tuple[dict[str, int], set[tuple[str, str, str, str]]]:
    key_map: dict[str, int] = {}
    identity_set: set[tuple[str, str, str, str]] = set()
    for row in conn.execute("SELECT id, case_title, source_work, target_work, target_text, raw_case_json FROM annotation_cases"):
        identity_set.add((row[1] or "", row[2] or "", row[3] or "", row[4] or ""))
        try:
            raw = json.loads(row[5] or "{}")
            key = raw.get("manual_case_key")
            if key:
                key_map[str(key)] = int(row[0])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return key_map, identity_set


def _source_document(conn: sqlite3.Connection, file_name: str) -> int:
    path = TEMPLATE_DIR / file_name
    lines = path.read_text(encoding="utf-8").splitlines()
    relative = str(path.relative_to(ROOT)).replace("\\", "/")
    conn.execute(
        """
        INSERT INTO source_documents(
            source_file_name, source_file_path, full_json_file, ai_json_file,
            doc_type, paragraph_count, comment_count, anchored_comment_count, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(source_file_name) DO UPDATE SET
            source_file_path=excluded.source_file_path,
            doc_type=excluded.doc_type,
            paragraph_count=excluded.paragraph_count,
            comment_count=excluded.comment_count,
            anchored_comment_count=excluded.anchored_comment_count,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            file_name,
            relative,
            "",
            "",
            "markdown_manual_annotation",
            sum(1 for line in lines if line.strip()),
            sum(1 for line in lines if line.startswith("### 批注")),
            sum(1 for line in lines if "- 锚定文字：" in line),
        ),
    )
    return int(conn.execute("SELECT id FROM source_documents WHERE source_file_name=?", (file_name,)).fetchone()[0])


def apply_manifest(manifest: dict[str, Any], backup: bool = True) -> dict[str, Any]:
    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)
    backup_path: Path | None = None
    if backup:
        backup_path = TMP_DIR / f"annotations.db.pre_markdown_ingest.{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
        shutil.copy2(DB_PATH, backup_path)
    inserted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        key_map, identity_set = _load_existing_cases(conn)
        for case in manifest["cases"]:
            key = str(case["key"])
            identity = (case["case_title"], case["source_work"], case["target_work"], case["target_text"])
            if key in key_map:
                skipped.append({"case_key": key, "existing_id": key_map[key], "reason": "idempotent_key"})
                continue
            if identity in identity_set:
                raise RuntimeError(f"unexpected_duplicate_identity:{key}:{identity}")
            source_id = _source_document(conn, case["source_file"])
            review = {
                "status": "two_agent_cross_checked",
                "reviewers": manifest["reviewers"],
                "case_key": key,
                "agent_a_report": str(REVIEW_A.relative_to(ROOT)).replace("\\", "/"),
                "agent_b_report": str(REVIEW_B.relative_to(ROOT)).replace("\\", "/"),
            }
            raw_case = {
                "schema_version": "manual_markdown_case.v1",
                "manual_case_key": key,
                "case_title": case["case_title"],
                "source_file": case["source_file"],
                "source_path": case["source_path"],
                "source_line_start": case["source_line_start"],
                "source_line_end": case["source_line_end"],
                "raw_case_text": case.get("raw_case_text", ""),
                "raw_markdown_body": case.get("raw_markdown", ""),
                "problem": case["problem"],
                "claim": case["claim"],
                "conclusion": case["conclusion"],
                "terms": _normalize_term_rows(case),
                "evidences": _normalize_evidence_rows(case),
                "process_steps": _normalize_step_rows(case),
                "uncertainties": case.get("uncertainties", []),
                "cross_validation": review,
            }
            cursor = conn.execute(
                """
                INSERT INTO annotation_cases(
                    source_document_id, case_title, source_work, target_work, target_text,
                    problem, claim, method_tags_json, conclusion, certainty, status, raw_case_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    source_id,
                    case["case_title"],
                    case["source_work"],
                    case["target_work"],
                    case["target_text"],
                    case["problem"],
                    case["claim"],
                    json.dumps(case["method_tags"], ensure_ascii=False),
                    case["conclusion"],
                    "待核",
                    "草稿",
                    json.dumps(raw_case, ensure_ascii=False),
                ),
            )
            case_id = int(cursor.lastrowid)
            for term in _normalize_term_rows(case):
                conn.execute(
                    """
                    INSERT INTO annotation_terms(
                        case_id, term, term_type, relation_type, related_term, note,
                        source_paragraph_indexes_json, source_comment_ids_json, raw_term_json
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        case_id,
                        term.get("term", ""),
                        term.get("term_type", "字词"),
                        term.get("relation_type", ""),
                        term.get("related_term", ""),
                        term.get("note", ""),
                        json.dumps(term.get("source_paragraph_indexes", []), ensure_ascii=False),
                        json.dumps(term.get("source_comment_ids", []), ensure_ascii=False),
                        json.dumps(term, ensure_ascii=False),
                    ),
                )
            for evidence in _normalize_evidence_rows(case):
                conn.execute(
                    """
                    INSERT INTO annotation_evidences(
                        case_id, evidence_type, work, quote, role, term,
                        source_paragraph_indexes_json, source_comment_ids_json, raw_evidence_json
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        case_id,
                        evidence.get("evidence_type", "书证"),
                        evidence.get("work", ""),
                        evidence.get("quote", ""),
                        evidence.get("role", "书证"),
                        evidence.get("term", ""),
                        json.dumps(evidence.get("source_paragraph_indexes", []), ensure_ascii=False),
                        json.dumps(evidence.get("source_comment_ids", []), ensure_ascii=False),
                        json.dumps(evidence, ensure_ascii=False),
                    ),
                )
            for step_order, step in enumerate(_normalize_step_rows(case), start=1):
                conn.execute(
                    """
                    INSERT INTO annotation_process_steps(
                        case_id, step_order, step_type, text,
                        source_paragraph_indexes_json, source_comment_ids_json, raw_step_json
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        case_id,
                        step_order,
                        step.get("step_type", "释理"),
                        step.get("text", ""),
                        json.dumps(step.get("source_paragraph_indexes", []), ensure_ascii=False),
                        json.dumps(step.get("source_comment_ids", []), ensure_ascii=False),
                        json.dumps(step, ensure_ascii=False),
                    ),
                )
            inserted.append({"case_key": key, "annotation_case_id": case_id, "source_document_id": source_id})
            key_map[key] = case_id
            identity_set.add(identity)
    result = {
        "manifest_version": manifest["manifest_version"],
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": str(DB_PATH.relative_to(ROOT)).replace("\\", "/"),
        "backup": str(backup_path.relative_to(ROOT)).replace("\\", "/") if backup_path else None,
        "inserted": inserted,
        "skipped": skipped,
        "duplicate_cases_skipped": manifest["duplicate_cases_skipped"],
        "reviewers": manifest["reviewers"],
    }
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Import cross-reviewed Markdown manual annotation cases.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate, but do not write annotations.db.")
    parser.add_argument("--no-backup", action="store_true", help="Do not make a pre-import database copy.")
    parser.add_argument("--database", type=Path, default=None, help="Override the SQLite database path for a test or controlled run.")
    parser.add_argument("--report", type=Path, default=None, help="Override the JSON report path.")
    args = parser.parse_args()
    global DB_PATH, REPORT_PATH
    if args.database:
        DB_PATH = args.database.resolve()
    if args.report:
        REPORT_PATH = args.report.resolve()
    manifest = build_manifest()
    if args.dry_run:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        dry_path = TMP_DIR / "manual_markdown_ingest_manifest.v1.json"
        dry_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "mode": "dry-run", "cases": len(manifest["cases"]), "manifest": str(dry_path)}, ensure_ascii=False))
        return 0
    result = apply_manifest(manifest, backup=not args.no_backup)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

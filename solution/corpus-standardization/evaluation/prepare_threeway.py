"""Build three-method, same-anchor comparison and separate blind packets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random

from prepare_comparison import connect, get_side

METHODS = ("baseline", "v2", "v3")
LABELS = ("A", "B", "C")
PAIRS = ("A:B", "A:C", "B:C")


def save(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(positions, baseline_directory, v2_directory, v3_directory, output):
    selected = json.loads(Path(positions).read_text(encoding="utf-8-sig"))
    if not isinstance(selected, dict) or not isinstance(selected.get("items"), list):
        raise ValueError("positions 须包含 items 列表")
    dbs = {method: connect(folder) for method, folder in zip(
        METHODS, (baseline_directory, v2_directory, v3_directory))}
    randomizer = random.Random(104729)
    items, blind, keys, seen = [], [], {}, set()
    try:
        for position in selected["items"]:
            case_id, path, anchor = position["id"], position["path"], position["anchor"]
            if case_id in seen:
                raise ValueError(f"重复样本 ID: {case_id}")
            seen.add(case_id)
            if not isinstance(anchor, int) or anchor < 0:
                raise ValueError(f"无效锚点: {case_id}")
            rows = {method: get_side(dbs[method], path, anchor) for method in METHODS}
            sources = {method: source for method, (source, _) in rows.items()}
            raw = sources["baseline"]["raw_text"]
            if any(source["raw_text"] != raw for source in sources.values()):
                raise ValueError(f"三种方法的原文不同: {path}")
            if any(source["body_start"] != sources["baseline"]["body_start"] for source in sources.values()):
                raise ValueError(f"三种方法的正文起点不同: {path}")
            reference_spans = []
            for span in position.get("reference_spans", []):
                start, end = span["start"], span["end"]
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(raw) or end - start > 1200:
                    raise ValueError(f"补充原文区间无效: {case_id}")
                reference_spans.append({"start": start, "end": end, "text": raw[start:end],
                                        "label": span.get("label", "补充原文")})
            methods = {}
            for method, (_, side) in rows.items():
                role = dbs[method].execute("SELECT role FROM chunks WHERE chunk_id=?", (side["chunk_id"],)).fetchone()
                methods[method] = {**side, "source_title": sources[method]["title"],
                                   "role": role["role"] if role else None}
            left = max(sources["baseline"]["body_start"], min(side["start"] for side in methods.values()) - 900)
            right = min(len(raw), max(side["end"] for side in methods.values()) + 900)
            common = {"id": case_id, "path": path, "title": sources["baseline"]["title"],
                      "collection": position["collection"], "anchor": anchor,
                      "form": position.get("form", position.get("forms", [])),
                      "context_start": left, "context_end": right, "source_context": raw[left:right],
                      "reference_spans": reference_spans}
            items.append({**common, "methods": methods, "annotation": {
                "comparisons": {reference: {"verdict": "undetermined", "reason": "尚未标注"}
                                for reference in ("v2", "baseline")}},
                "review": {"status": "pending"}})
            order = list(METHODS)
            randomizer.shuffle(order)
            key = dict(zip(LABELS, order))
            keys[case_id] = key
            sides = {label: {k: methods[method][k] for k in (
                "source_title", "role", "start", "end", "text", "heading", "reading_start", "reading_end", "reading_text")}
                     for label, method in key.items()}
            blind.append({**common, **sides})
    finally:
        for db in dbs.values():
            db.close()

    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    save(destination / "comparison.json", {"schema": "threeway.v1", "methodology": {
        "methods": {"baseline": "固定600字窗口，重叠100字", "v2": "结构版；无自然边界时回退为600字窗口、重叠100字",
                    "v3": "新版结构版；无自然边界时约600字顺序硬切、无重叠"},
        "scoring": "A/B/C 匿名。五维问题各取 0/1/2/null，越低越好；三组两两判定可选 tie 或 undetermined。长度只展示，不自动判优。",
        "limits": "AI 初评与主agent复核分开保存；局部样本不代表全库或下游检索效果。v3与v2差异还包含无自然边界时的兜底窗口与重叠策略，不能全归因于标题或跨片关联。"},
        "summary": {"total": len(items), "reviewed": 0}, "items": items})
    save(destination / "blind_packets.json", {"schema": "threeway-blind.v1",
        "instructions": "只读取本文件。对 A/B/C 分别打五维 0/1/2/null，并为 A:B、A:C、B:C 各填写 preferred=A/B/C/tie/undetermined（只可选该对中的字母）、reason。长度不是改善证据；阅读窗口另作备注。",
        "dimensions": ["missing_heading", "cut_note", "detached_note", "unrelated", "cut_body"],
        "pairwise": list(PAIRS), "items": blind})
    save(destination / "method_key.json", keys)
    return {"samples": len(items), "output": str(destination)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--v2", required=True)
    parser.add_argument("--v3", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.positions, args.baseline, args.v2, args.v3, args.output), ensure_ascii=False))

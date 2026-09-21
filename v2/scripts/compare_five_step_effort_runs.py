#!/usr/bin/env python3
"""Compare two collected five-step runs against material-level gold cues.

This is a lightweight, deterministic comparison aid.  It does not decide the
scholarly truth of a case; it checks whether each output carries the human
gold's explicit core points, whether the conclusion states the claim before
the verification boundary, and whether obvious engineering language leaks
into the reader-facing draft.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


EFFORTS = ("none", "low", "high", "max")
STEP_FIELDS = (
    "problem_discovery",
    "research_question",
    "evidence_collection",
    "reasoning",
    "conclusion",
)


def load_run(directory: Path, effort: str) -> dict[str, Any]:
    path = directory / f"effort-{effort}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def draft_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    draft = payload.get("draft")
    return draft if isinstance(draft, list) else []


def step_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(step.get("field")): step for step in draft_steps(payload)}


def all_text(payload: dict[str, Any]) -> str:
    return "\n".join(str(step.get("text", "")) for step in draft_steps(payload))


def conclusion(payload: dict[str, Any]) -> str:
    return step_map(payload).get("conclusion", {}).get("text", "")


def usage_value(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get("usage", {}).get(key)
    return int(value) if isinstance(value, (int, float)) else None


def reasoning_tokens(payload: dict[str, Any]) -> int | None:
    details = payload.get("usage", {}).get("completion_tokens_details", {})
    value = details.get("reasoning_tokens")
    if isinstance(value, (int, float)):
        return int(value)
    legacy = payload.get("usage", {}).get("reasoning_tokens")
    return int(legacy) if isinstance(legacy, (int, float)) else None


def contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def gold_cues(payload: dict[str, Any]) -> dict[str, bool]:
    text = all_text(payload)
    return {
        "target_phrase": "薄言有之" in text and "芣苡" in text,
        "mao_old_reading": "毛传" in text and "藏" in text,
        "wang_claim": contains_any(text, (r"有亦取", r"有[^。；\n]{0,12}(?:训|訓|作|为|為|当训|當訓)[^。；\n]{0,8}取")),
        "claim_attributed": contains_any(text, (r"家大人", r"王氏", r"王引之")),
        "guangya": contains_any(text, (r"广雅", r"廣雅")),
        "zhanyang": "瞻卬" in text,
        "chapter_progression": contains_any(text, (r"章次", r"次第")) and "掇" in text and "捋" in text,
        "no_repetition_rule": "不嫌" in text and contains_any(text, (r"复", r"複")),
    }


def decisive_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    text = all_text(payload)
    final = conclusion(payload)
    claim_patterns = (r"有亦取", r"有[^。；\n]{0,12}(?:训|訓|作|为|為|当训|當訓)[^。；\n]{0,8}取")
    claim_match = next((match for pattern in claim_patterns for match in re.finditer(pattern, text)), None)
    final_claim_match = next((match for pattern in claim_patterns for match in re.finditer(pattern, final)), None)
    boundary_patterns = (r"尚未", r"未确认", r"未確[認定]", r"未完成", r"不能.*(?:定论|定論|最终|最終)", r"无法.*(?:判断|判斷|确定|確定)")
    boundary_match = next((match for pattern in boundary_patterns for match in re.finditer(pattern, final)), None)
    engineering = contains_any(text, (r"evidence_index", r"source_resolution", r"case_id", r"quote_check", r"external_source"))
    unsupported_identity = bool(re.search(r"家大人.{0,8}[（(]\s*王念孙|家大人.{0,8}王念孫", text))
    scores = {
        "claim_anywhere": bool(claim_match),
        "claim_in_conclusion": bool(final_claim_match),
        "claim_before_boundary": bool(final_claim_match and (not boundary_match or final_claim_match.start() < boundary_match.start())),
    }
    scores["decisiveness_score"] = sum(scores.values())
    return {
        **scores,
        "has_verification_boundary": bool(boundary_match),
        "engineering_language": engineering,
        "unsupported_identity_risk": unsupported_identity,
        "claim_excerpt": claim_match.group(0) if claim_match else None,
        "conclusion_chars": len(final),
        "step_chars": {field: len(step_map(payload).get(field, {}).get("text", "")) for field in STEP_FIELDS},
        "review_question_count": sum(len(step.get("review_questions", [])) for step in draft_steps(payload)),
    }


def record(directory: Path, effort: str) -> dict[str, Any]:
    payload = load_run(directory, effort)
    cues = gold_cues(payload)
    decisive = decisive_metrics(payload)
    return {
        "effort": effort,
        "ok": bool(payload.get("ok")),
        "prompt_version": payload.get("prompt_version"),
        "model": payload.get("model_returned") or payload.get("model_requested"),
        "generated_at": payload.get("generated_at"),
        "usage": {
            "prompt_tokens": usage_value(payload, "prompt_tokens"),
            "completion_tokens": usage_value(payload, "completion_tokens"),
            "reasoning_tokens": reasoning_tokens(payload),
            "total_tokens": usage_value(payload, "total_tokens"),
        },
        "gold_cues": cues,
        "gold_cues_total": sum(cues.values()),
        "decisive": decisive,
        "conclusion": conclusion(payload),
    }


def markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| effort | total tokens | reasoning | gold cues | decisive | claim before boundary | unsupported identity | questions |",
        "|---|---:|---:|---:|---:|---|---|---:|",
    ]
    for row in rows:
        usage = row["usage"]
        decisive = row["decisive"]
        lines.append(
            "| {effort} | {total} | {reasoning} | {gold}/8 | {score}/3 | {before} | {identity} | {questions} |".format(
                effort=row["effort"],
                total=usage["total_tokens"] if usage["total_tokens"] is not None else "—",
                reasoning=usage["reasoning_tokens"] if usage["reasoning_tokens"] is not None else "—",
                gold=row["gold_cues_total"],
                score=decisive["decisiveness_score"],
                before="是" if decisive["claim_before_boundary"] else "否",
                identity="是" if decisive["unsupported_identity_risk"] else "否",
                questions=decisive["review_question_count"],
            )
        )
    return "\n".join(lines)


def build_report(baseline_dir: Path, candidate_dir: Path, baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> str:
    case_id = load_run(candidate_dir, "none").get("case_id")
    baseline_version = baseline[0].get("prompt_version") if baseline else "unknown"
    candidate_version = candidate[0].get("prompt_version") if candidate else "unknown"
    by_effort = {row["effort"]: row for row in candidate}
    baseline_by_effort = {row["effort"]: row for row in baseline}
    lines = [
        "# 五步释证 prompt 对比",
        "",
        f"- 案例：`{case_id}`",
        f"- 基线：`{baseline_version}`（目录 `{baseline_dir}`）",
        f"- 新版：`{candidate_version}`（目录 `{candidate_dir}`）",
        "- gold 口径：人工标注中的考据对象、毛传旧训、王氏明确主张、三类书证/章次依据；gold 只检查材料是否被正确带出，不把 AI 的谨慎边界误判为错误。",
        "",
        "## 新版总体结果",
        "",
        markdown_table(candidate),
        "",
        "## 与 v4 的逐 effort 对比",
        "",
        "| effort | v4 decisive | v5 decisive | v4 conclusion chars | v5 conclusion chars | v4 questions | v5 questions | v5 新增风险 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for effort in EFFORTS:
        old = baseline_by_effort.get(effort)
        new = by_effort.get(effort)
        if not old or not new:
            continue
        old_d = old["decisive"]
        new_d = new["decisive"]
        risk = "家大人身份被补成王念孙" if new_d["unsupported_identity_risk"] else "无明显身份补造"
        lines.append(
            f"| {effort} | {old_d['decisiveness_score']}/3 | {new_d['decisiveness_score']}/3 | "
            f"{old_d['conclusion_chars']} | {new_d['conclusion_chars']} | "
            f"{old_d['review_question_count']} | {new_d['review_question_count']} | {risk} |"
        )
    lines.extend(["", "## 逐 effort 结论文本", ""])
    for effort in EFFORTS:
        old = baseline_by_effort.get(effort)
        new = by_effort.get(effort)
        if not old or not new:
            continue
        lines.extend([
            f"### {effort}",
            "",
            "**v4：**",
            "",
            old["conclusion"],
            "",
            "**v5：**",
            "",
            new["conclusion"],
            "",
            f"gold cues：{', '.join(key for key, value in new['gold_cues'].items() if value)}。",
            f"v5 结论先给主张再给边界：{'是' if new['decisive']['claim_before_boundary'] else '否'}；工程字段泄漏：{'有' if new['decisive']['engineering_language'] else '无'}。",
            "",
        ])
    lines.extend([
        "## 解释",
        "",
        "v5 的目标不是让模型把未核验的原典说成已核验，而是把“材料明确记载的作者主张”和“项目尚未完成的独立核验”拆开。因而“有亦取也”应先作为王氏所载判断直接写出，随后再交代版本边界。",
        "",
        "若出现“家大人（王念孙）”而材料本身没有具名，这属于新增无据身份信息；应在下一版 prompt 中明确禁止自行补名，保留“家大人”或“材料所称家大人”。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    baseline = [record(args.baseline_dir, effort) for effort in EFFORTS]
    candidate = [record(args.candidate_dir, effort) for effort in EFFORTS]
    result = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "baseline_dir": str(args.baseline_dir),
        "candidate_dir": str(args.candidate_dir),
        "efforts": list(EFFORTS),
        "baseline": baseline,
        "candidate": candidate,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text(build_report(args.baseline_dir, args.candidate_dir, baseline, candidate), encoding="utf-8")
    print(json.dumps({"output_json": str(args.output_json), "output_md": str(args.output_md)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

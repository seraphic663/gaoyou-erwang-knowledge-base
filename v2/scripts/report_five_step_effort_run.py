#!/usr/bin/env python3
"""Write a detailed, reader-facing comparison of one v5 effort sweep."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compare_five_step_effort_runs import EFFORTS, STEP_FIELDS, decisive_metrics, gold_cues, load_run


STEP_LABELS = {
    "problem_discovery": "发疑",
    "research_question": "设问",
    "evidence_collection": "取证",
    "reasoning": "释理",
    "conclusion": "结论",
}


def steps_by_field(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(step.get("field")): step for step in payload.get("draft", [])}


def usage(payload: dict[str, Any], key: str) -> str:
    value = payload.get("usage", {}).get(key)
    return str(value) if value is not None else "—"


def reasoning_tokens(payload: dict[str, Any]) -> str:
    value = payload.get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens")
    return str(value) if value is not None else "—"


def retrieval_summary(payload: dict[str, Any]) -> dict[str, Any]:
    retrieval = payload.get("retrieval_materials") or {}
    items = retrieval.get("items") or []
    first = items[0] if items else {}
    return {
        "query": retrieval.get("query") or "—",
        "work_key": retrieval.get("work_key") or "—",
        "count": retrieval.get("returned_count", retrieval.get("candidate_count", len(items))),
        "document": first.get("document_title") or "—",
        "entry": first.get("entry_title") or "—",
        "location": first.get("local_ordinal") or "—",
        "match_reason": first.get("match_reason") or "—",
    }


def effort_interpretation(effort: str, metrics: dict[str, Any]) -> str:
    if effort == "none":
        return "最短且已经完成核心任务：直接说出“有”训“取”，同时保留版本核验边界；每步只有 2 个待核问题，适合快速初筛。它没有显式 reasoning token，解释链仍然足够，但细节最少。"
    if effort == "low":
        return "四档中最紧凑的完整版本：五步均覆盖 gold，结论字数最短，但从设问到章次、书证的连接完整。它把人工问题扩展到每步 3 个，适合日常审校和控制成本。"
    if effort == "high":
        return "细节与克制的平衡最好：取证和释理比 low 更展开，仍只使用材料中的“家大人”称谓，没有新增身份事实。它适合作为默认审校 effort。"
    risk = "出现材料未具名的“家大人（王念孙）”身份补全；按本项目证据边界，这是新增无据信息。"
    return f"输出最长、推理 token 最多，能把词汇、对文和章次拆得最细；但有一项明确回归风险：{risk} max 不应因更有时间思考就引入材料外知识。"


def build_report(run_dir: Path) -> str:
    payloads = {effort: load_run(run_dir, effort) for effort in EFFORTS}
    metrics = {effort: decisive_metrics(payloads[effort]) for effort in EFFORTS}
    cues = {effort: gold_cues(payloads[effort]) for effort in EFFORTS}
    retrieval = retrieval_summary(payloads["none"])
    case_id = payloads["none"].get("case_id", "—")
    prompt_version = payloads["none"].get("prompt_version", "—")
    model = payloads["none"].get("model_returned") or payloads["none"].get("model_requested") or "—"

    lines = [
        f"# {prompt_version} 四 effort 细致对比",
        "",
        f"- 案例：`{case_id}`",
        f"- prompt：`{prompt_version}`",
        f"- 模型：`{model}`",
        "- 数据来源：同一次 Railway API sweep；四个 effort 使用同一案例、同一检索材料、同一输出 schema。",
        "- gold 口径：人工标注中的 8 个可观察核心点。这里测的是核心点召回和证据边界，不把文本长度当成学术正确率。",
        "",
        "## 1. 固定的检索输入",
        "",
        f"四个 effort 的检索词都是“{retrieval['query']}”，作品范围是 `{retrieval['work_key']}`，返回 {retrieval['count']} 条原文。命中材料为《{retrieval['document']}》的“{retrieval['entry']}”，位置 {retrieval['location']}，命中原因是“{retrieval['match_reason']}”。因此，effort 之间的差异来自模型生成过程，不是检索结果变化。",
        "",
        "## 2. 量化结果",
        "",
        "| effort | 总 token | reasoning token | 五步总字数 | 结论字数 | 待核问题 | gold | 结论先主张后边界 | 工程字段泄漏 | 新增身份风险 |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for effort in EFFORTS:
        payload = payloads[effort]
        metric = metrics[effort]
        total_chars = sum(metric["step_chars"].values())
        lines.append(
            f"| {effort} | {usage(payload, 'total_tokens')} | {reasoning_tokens(payload)} | {total_chars} | "
            f"{metric['conclusion_chars']} | {metric['review_question_count']} | {sum(cues[effort].values())}/8 | "
            f"{'是' if metric['claim_before_boundary'] else '否'} | "
            f"{'有' if metric['engineering_language'] else '无'} | "
            f"{'有' if metric['unsupported_identity_risk'] else '无'} |"
        )
    lines.extend([
        "",
        "解释：四档都达到 8/8 gold，说明 v5 已经解决了 v4 none 的“核心判断被边界说明压住”问题。但 8/8 只是召回指标；max 的身份补全说明，召回高并不代表没有新增无据事实。",
        "",
        "## 3. gold 核心点逐项检查",
        "",
        "| 核心点 | none | low | high | max |",
        "|---|---|---|---|---|",
    ])
    cue_labels = {
        "target_phrase": "考据对象：芣苡“薄言有之”",
        "mao_old_reading": "毛传旧训：有，藏之也",
        "wang_claim": "王氏主张：有亦取也",
        "claim_attributed": "主张有归属（家大人/王氏/王引之）",
        "guangya": "《广雅》书证",
        "zhanyang": "《大雅·瞻卬》书证",
        "chapter_progression": "章次：掇、捋等递进论证",
        "no_repetition_rule": "《诗》用词不嫌于复",
    }
    for key, label in cue_labels.items():
        lines.append(f"| {label} | " + " | ".join("是" if cues[effort][key] else "否" for effort in EFFORTS) + " |")

    lines.extend(["", "## 4. 逐 effort 细读", ""])
    for effort in EFFORTS:
        payload = payloads[effort]
        metric = metrics[effort]
        step_map = steps_by_field(payload)
        lines.extend([
            f"### {effort}",
            "",
            effort_interpretation(effort, metric),
            "",
            "| 步骤 | 字数 | evidence_refs | 待核问题数 |",
            "|---|---:|---|---:|",
        ])
        for field in STEP_FIELDS:
            step = step_map.get(field, {})
            refs = ", ".join(str(ref) for ref in step.get("evidence_refs", [])) or "—"
            lines.append(f"| {STEP_LABELS[field]} | {len(str(step.get('text', '')))} | {refs} | {len(step.get('review_questions', []))} |")
        lines.extend(["", "#### 五步原文", ""])
        for field in STEP_FIELDS:
            step = step_map.get(field, {})
            lines.extend([
                f"**{STEP_LABELS[field]}**",
                "",
                str(step.get("text", "")).strip(),
                "",
                "待核问题：" + ("；".join(str(question).strip() for question in step.get("review_questions", [])) or "无"),
                "",
            ])

    lines.extend([
        "## 5. 横向结论",
        "",
        "1. none 已足够完成第一轮判断：它没有因为 effort 为 none 就漏掉“毛传—王氏—广雅—瞻卬—章次”这条核心链条。",
        "2. low 是成本和信息量最平衡的版本；它比 none 多出更完整的待核清单，但没有明显增加无据断言。",
        "3. high 是本案例最适合作为默认审校的版本：比 low 更细地说明证据作用和推理链，同时没有 max 的身份补造。",
        "4. max 的新增内容主要是展开和边界，不是新的证据。它的“王念孙”属于材料外身份推断，不能因为 effort 更高而接受。",
        "5. 四个 effort 的 evidence_refs 都只引用编号 0，且没有把检索序号冒充 evidence_refs；这部分边界控制是稳定的。",
        "",
        "## 6. 下一版 prompt 的唯一必要补丁",
        "",
        "在 v5 末尾加入：`材料只写“家大人”时，不得依据常识补出姓名；只有材料明确具名时才可写姓名。不要把来源作品作者、传统称谓或模型记忆当作本案材料。` 其余 decisive 规则建议保留。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_report(args.run_dir), encoding="utf-8")
    print(json.dumps({"output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

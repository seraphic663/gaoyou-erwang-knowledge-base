"""Join anonymous three-way ratings and explicit review overrides."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import statistics

DIMENSIONS = ("missing_heading", "cut_note", "detached_note", "unrelated", "cut_body")
LABELS = ("A", "B", "C")
PAIRS = ("A:B", "A:C", "B:C")
REFERENCES = ("v2", "baseline")
VERDICTS = ("improved", "regressed", "tied", "undetermined")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checked_scores(scores, case_id):
    if not isinstance(scores, dict) or set(scores) != set(DIMENSIONS) or any(
        value not in (0, 1, 2, None) or isinstance(value, bool) for value in scores.values()
    ):
        raise ValueError(f"无效五维分数: {case_id}")


def make_annotation(rated, key):
    case_id = rated["id"]
    methods = {}
    for label in LABELS:
        note = rated[label]
        checked_scores(note.get("scores"), case_id)
        methods[key[label]] = {"scores": note["scores"], "reason": note.get("reason", ""),
                               "uncertain": any(value is None for value in note["scores"].values())}
    judgments = rated.get("pairwise")
    if not isinstance(judgments, dict) or set(judgments) != set(PAIRS):
        raise ValueError(f"须提供 A:B、A:C、B:C 三组判定: {case_id}")
    by_method = {}
    for pair in PAIRS:
        labels = pair.split(":")
        judgment = judgments[pair]
        if not isinstance(judgment, dict):
            raise ValueError(f"判定格式错误: {case_id}:{pair}")
        preferred = judgment.get("preferred")
        if preferred not in (*labels, "tie", "undetermined"):
            raise ValueError(f"判定选择错误: {case_id}:{pair}")
        names = [key[label] for label in labels]
        by_method[":".join(names)] = {"preferred": key[preferred] if preferred in labels else preferred,
                                        "reason": judgment.get("reason", "")}
    comparisons = {}
    for reference in REFERENCES:
        matched = next(value for pair, value in by_method.items()
                       if set(pair.split(":")) == {"v3", reference})
        preferred = matched["preferred"]
        verdict = ("tied" if preferred == "tie" else "undetermined" if preferred == "undetermined"
                   else "improved" if preferred == "v3" else "regressed")
        comparisons[reference] = {"verdict": verdict, "reason": matched["reason"]}
    return {"methods": methods, "comparisons": comparisons, "pairwise": by_method,
            "reading_note": rated.get("reading_note", ""),
            "extra_source_ranges": rated.get("extra_source_ranges", [])}


def apply_review(annotation, override, case_id):
    if not isinstance(override, dict):
        raise ValueError(f"复核覆盖字段须为对象: {case_id}")
    for method, note in override.get("methods", {}).items():
        if method not in ("baseline", "v2", "v3"):
            raise ValueError(f"未知方法: {case_id}:{method}")
        current = annotation["methods"][method]
        if "scores" in note:
            scores = {**current["scores"], **note["scores"]}
            checked_scores(scores, case_id)
            current["scores"] = scores
            current["uncertain"] = any(value is None for value in scores.values())
        if "reason" in note:
            current["reason"] = note["reason"]
    for reference, judgment in override.get("comparisons", {}).items():
        if reference not in REFERENCES or judgment.get("verdict") not in VERDICTS:
            raise ValueError(f"复核判定错误: {case_id}:{reference}")
        annotation["comparisons"][reference].update(judgment)
    if "reading_note" in override:
        annotation["reading_note"] = override["reading_note"]
    if "extra_source_ranges" in override:
        annotation["extra_source_ranges"] = override["extra_source_ranges"]


def finalize(directory, annotation_paths, review_path=None):
    directory = Path(directory)
    data, keys = read(directory / "comparison.json"), read(directory / "method_key.json")
    if data.get("schema") != "threeway.v1":
        raise ValueError("不是 threeway.v1 对比文件")
    annotations = {}
    for path in annotation_paths:
        for rated in read(path)["items"]:
            case_id = rated["id"]
            if case_id in annotations:
                raise ValueError(f"重复初评: {case_id}")
            annotations[case_id] = rated
    expected = {item["id"] for item in data["items"]}
    if set(annotations) != expected or set(keys) != expected:
        raise ValueError("初评、匿名键与样本位置不一致")
    reviews = {}
    if review_path:
        for review in read(review_path)["items"]:
            case_id = review["id"]
            if case_id in reviews or case_id not in expected:
                raise ValueError(f"复核 ID 重复或未知: {case_id}")
            reviews[case_id] = review
    for item in data["items"]:
        case_id = item["id"]
        key = keys[case_id]
        if set(key) != set(LABELS) or set(key.values()) != {"baseline", "v2", "v3"}:
            raise ValueError(f"匿名键错误: {case_id}")
        initial = make_annotation(annotations[case_id], key)
        item["initial_annotation"] = initial
        item["annotation"] = deepcopy(initial)
        # Pairwise choices are the anonymous first pass. Reviewed comparisons below
        # are the only current verdicts; retaining both here could contradict a review.
        item["annotation"].pop("pairwise")
        item["review"] = {"status": "not_reviewed", "note": "匿名初评，尚未由主agent复核"}
        if case_id in reviews:
            review = reviews[case_id]
            apply_review(item["annotation"], review.get("annotation", {}), case_id)
            item["review"] = {k: v for k, v in review.items() if k != "id"}
    summary = {"total": len(data["items"]),
               "reviewed": sum(item["review"].get("status") == "reviewed" for item in data["items"]),
               "comparisons": {}, "initial_comparisons": {}}
    for reference in REFERENCES:
        for field, target in (("annotation", "comparisons"), ("initial_annotation", "initial_comparisons")):
            counts = Counter(item[field]["comparisons"][reference]["verdict"] for item in data["items"])
            summary[target][reference] = {name: counts[name] for name in VERDICTS}
    summary["changed_verdict_ids"] = {
        reference: [item["id"] for item in data["items"] if
                    item["annotation"]["comparisons"][reference]["verdict"] !=
                    item["initial_annotation"]["comparisons"][reference]["verdict"]]
        for reference in REFERENCES}
    summary["lengths"] = {}
    for method in ("baseline", "v2", "v3"):
        lengths = [len(item["methods"][method]["text"]) for item in data["items"]]
        summary["lengths"][method] = {
            "mean": round(statistics.mean(lengths), 1) if lengths else None,
            "median": statistics.median(lengths) if lengths else None,
            "min": min(lengths) if lengths else None,
            "max": max(lengths) if lengths else None,
        }
    data["summary"] = summary
    save(directory / "comparison.json", data)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--annotations", nargs="+", required=True)
    parser.add_argument("--reviews")
    args = parser.parse_args()
    print(json.dumps(finalize(args.directory, args.annotations, args.reviews), ensure_ascii=False, indent=2))

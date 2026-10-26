"""Assemble the frozen small-boundary run and reconciled scores for local review."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUN = HERE / "runs" / "20261025T113349Z"
NOTE_RE = re.compile(r"^\s*([012])\s*,\s*([012])\s*,\s*([012])\s*[。.]?\s*(.*)$", re.S)
FIELDS = ("role_score", "attachment_score", "quotation_score")
CATEGORY_NAMES = {
    "音注": "音注", "sound_note": "音注",
    "校记": "校记", "textual_note": "校记",
    "引文内插注": "引文内插注", "quote_inline_note": "引文内插注",
    "short_bare_note": "裸短音注",
}


def read_json(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def unique_by(items, key):
    output = {}
    for item in items:
        identity = key(item)
        if identity in output:
            raise ValueError(f"duplicate identity: {identity}")
        output[identity] = item
    return output


def source_line(reference, text):
    path = ROOT / reference["path"]
    original = path.read_text(encoding="utf-8-sig")
    start, end = reference["start_cp"], reference["end_cp"]
    if original[start:end] != text:
        raise ValueError(f"source span mismatch: {reference['id']}")
    return original.count("\n", 0, start) + 1


def reference_text(reference):
    gold = reference["hidden_gold"]
    parts = []
    for label, key in (
        ("判读", "function"),
        ("可用底本文字", "base_text_exact"),
        ("证据限度", "uncertainty"),
    ):
        value = gold.get(key)
        if value:
            parts.append(f"{label}：{value}")
    return "\n".join(parts) or json.dumps(gold, ensure_ascii=False, indent=2)


def main():
    public = read_json("public_inputs.json")["items"]
    references = read_json("hidden_reference.json")["items"]
    key = read_json("scoring_key.json")
    initial = read_json("scores_a.json")["items"] + read_json("scores_b.json")["items"]
    notes = read_json("primary_notes_final.json")
    attempts = [json.loads(line) for line in (RUN / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]
    metadata = json.loads((RUN / "metadata.json").read_text(encoding="utf-8"))
    run_stats = json.loads((RUN / "run_stats.json").read_text(encoding="utf-8"))

    assert len(public) == len(references) == 21
    assert [x["id"] for x in public] == [x["id"] for x in references]
    assert len(key) == len(initial) == len(notes) == len(attempts) == 84
    assert len({x["id"] for x in public}) == 21
    assert all(x["http_status"] == 200 and x["attempt"] == 1 for x in attempts)
    assert run_stats["completed"] == run_stats["attempts"] == 84

    keyed = unique_by(key.items(), lambda pair: (pair[1]["id"], pair[1]["repeat"], pair[1]["condition"]))
    scored = unique_by(initial, lambda item: item["response_id"])
    attempt_map = unique_by(attempts, lambda item: (item["id"], item["repeat"], item["condition"]))
    expected = {(x["id"], repeat, condition) for x in public for repeat in (1, 2) for condition in ("tagged", "untagged")}
    assert set(keyed) == set(attempt_map) == expected
    assert {f"{case}/{repeat}/{condition}" for case, repeat, condition in expected} == set(notes)
    assert set(scored) == set(key)

    cases = []
    changed = []
    format_responses = []
    for source, reference in zip(public, references):
        case_id = source["id"]
        variants = []
        for condition in ("tagged", "untagged"):
            for repeat in (1, 2):
                identity = (case_id, repeat, condition)
                response_id, _ = keyed[identity]
                attempt = attempt_map[identity]
                old = scored[response_id]
                if old["case_id"] != case_id:
                    raise ValueError(f"score/key mismatch: {response_id}")
                note = notes[f"{case_id}/{repeat}/{condition}"]
                match = NOTE_RE.match(note)
                if not match:
                    raise ValueError(f"unparseable final note: {identity}")
                values = tuple(map(int, match.group(1, 2, 3)))
                score = dict(zip(FIELDS, values))
                score.update({"critical_error": False, "reason": match.group(4).strip()})
                api_response = json.loads(attempt["response"])
                answer = api_response["choices"][0]["message"]["content"]
                if not isinstance(answer, str):
                    raise ValueError(f"missing raw answer: {identity}")
                issues = attempt.get("format_issues") or []
                if issues:
                    format_responses.append(response_id)
                score_changed = any(old[field] != score[field] for field in FIELDS) or bool(old["critical_error"])
                if score_changed:
                    changed.append(response_id)
                variants.append({
                    "condition": condition,
                    "repeat": repeat,
                    "response_id": response_id,
                    "answer": answer,
                    "score": score,
                    "initial_score": old,
                    "changed_initial_score": score_changed,
                    "format_issues": issues,
                    "http_status": attempt["http_status"],
                    "outcome": attempt["outcome"],
                    "other_commentary_as_body": case_id == "SOL03" and condition == "tagged",
                })
        cases.append({
            "id": case_id,
            "path": reference["path"],
            "line": source_line(reference, source["text"]),
            "target": source["target_quote"],
            "text": source["text"],
            "category": CATEGORY_NAMES[reference["category"]],
            "raw_category": reference["category"],
            "reference": reference_text(reference),
            "reference_uncertain": case_id in ("luna-01", "luna-02", "SOLH03"),
            "reference_detail": reference["hidden_gold"],
            "variants": variants,
        })

    counts = Counter()
    for case in cases:
        for variant in case["variants"]:
            condition = variant["condition"]
            score = variant["score"]
            for field in FIELDS:
                counts[(condition, field)] += score[field] == 2
            counts[(condition, "full")] += all(score[field] == 2 for field in FIELDS)
            counts[(condition, "critical")] += score["critical_error"]
            counts[(condition, "other_commentary_as_body")] += variant["other_commentary_as_body"]
    expected_counts = {
        ("tagged", "role_score"): 42, ("tagged", "attachment_score"): 42,
        ("tagged", "quotation_score"): 32, ("tagged", "full"): 32,
        ("untagged", "role_score"): 40, ("untagged", "attachment_score"): 40,
        ("untagged", "quotation_score"): 37, ("untagged", "full"): 35,
    }
    for name, value in expected_counts.items():
        if counts[name] != value:
            raise ValueError(f"unexpected reconciled count {name}: {counts[name]} != {value}")
    if (len(format_responses) != 4 or counts[("tagged", "critical")] or counts[("untagged", "critical")]
            or counts[("tagged", "other_commentary_as_body")] != 2
            or counts[("untagged", "other_commentary_as_body")] != 0):
        raise ValueError("format or central-critical count mismatch")

    summary = {
        "cases": 21,
        "requests": 84,
        "requests_per_condition": 42,
        "paired_repeats": 42,
        "tagged_correct": counts[("tagged", "full")],
        "untagged_correct": counts[("untagged", "full")],
        "tagged_critical": counts[("tagged", "critical")],
        "untagged_critical": counts[("untagged", "critical")],
        "tagged_other_commentary_as_body": counts[("tagged", "other_commentary_as_body")],
        "untagged_other_commentary_as_body": counts[("untagged", "other_commentary_as_body")],
        "perfect_dimension_counts": {
            condition: {field: counts[(condition, field)] for field in FIELDS}
            for condition in ("tagged", "untagged")
        },
        "format_issue_response_ids": sorted(format_responses),
        "changed_initial_response_ids": sorted(changed),
        "changed_initial_response_count": len(changed),
        "http_200": 84,
        "retries": 0,
    }
    result = {
        "summary": summary,
        "provenance": {
            "run": str(RUN.relative_to(HERE)).replace("\\", "/"),
            "model": metadata["model"],
            "reasoning_effort": metadata["reasoning_effort"],
            "input_sha256": metadata["input_sha256"],
            "prompt_sha256": metadata["prompt_sha256"],
            "final_scoring_source": "primary_notes_final.json",
            "initial_scoring_sources": ["scores_a.json", "scores_b.json"],
        },
        "cases": cases,
    }
    output = HERE / "results.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output.name}; changed initial scores: {len(changed)}; format responses: {len(format_responses)}")
    print("changed response ids:", ", ".join(sorted(changed)))


if __name__ == "__main__":
    main()

"""Run the case2query2retrieve benchmark against local or deployed HTTP APIs."""

from __future__ import annotations

import argparse
import json
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "benchmarks" / "case2query2retrieve.v1.json"


def fetch_json(base_url: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v2/retrieve?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"request_failed:{error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("response_not_object")
    if payload.get("ok") is False:
        raise RuntimeError(str(payload.get("message") or "retrieval_not_ok"))
    return payload


def request_for_item(base_url: str, item: dict[str, Any], timeout: float) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": 20}
    if item.get("mode", "case") == "query":
        params.update({"q": item.get("query", ""), "work_key": item.get("work_key", "")})
    else:
        params["case_id"] = item.get("case_id", "")
    return fetch_json(base_url, params, timeout)


def item_result(item: dict[str, Any], payload: dict[str, Any] | None, error: str | None) -> dict[str, Any]:
    gold = {str(value) for value in item.get("gold_passage_ids", [])}
    hard_negative = {str(value) for value in item.get("hard_negative_ids", [])}
    if error:
        return {
            "sample_id": item.get("sample_id"),
            "evaluation": item.get("evaluation"),
            "class": item.get("class"),
            "error": error,
            "gold_rank": None,
            "items": [],
        }

    rows = payload.get("items") or []
    ranked = []
    gold_rank = None
    hard_negative_ranks: dict[str, int] = {}
    expected_work = item.get("work_key")
    scope_violations = 0
    for rank, row in enumerate(rows, start=1):
        passage_id = str(row.get("passage_id") or "")
        if passage_id in gold and gold_rank is None:
            gold_rank = rank
        if passage_id in hard_negative:
            hard_negative_ranks[passage_id] = rank
        if expected_work and row.get("work_key") != expected_work:
            scope_violations += 1
        ranked.append({
            "rank": rank,
            "passage_id": passage_id,
            "work_key": row.get("work_key"),
            "score": row.get("score"),
            "match_reason": row.get("match_reason"),
        })
    return {
        "sample_id": item.get("sample_id"),
        "evaluation": item.get("evaluation"),
        "class": item.get("class"),
        "case_id": item.get("case_id"),
        "query": payload.get("query"),
        "query_quality": payload.get("query_quality"),
        "work_key": payload.get("work_key"),
        "candidate_count": payload.get("candidate_count"),
        "returned_count": payload.get("returned_count", len(rows)),
        "fallback_from_work_key": (payload.get("trace") or {}).get("fallback_from_work_key"),
        "gold_rank": gold_rank,
        "hard_negative_ranks": hard_negative_ranks,
        "scope_violations": scope_violations,
        "items": ranked,
    }


def summarize(results: list[dict[str, Any]], *, evaluation: str) -> dict[str, Any]:
    selected = [row for row in results if row.get("evaluation") == evaluation]
    errors = [row for row in selected if row.get("error")]
    ranks = [int(row["gold_rank"]) for row in selected if row.get("gold_rank")]
    primary_count = len(selected)
    summary: dict[str, Any] = {
        "sample_count": primary_count,
        "errors": len(errors),
        "error_sample_ids": [row.get("sample_id") for row in errors],
        "gold_hits": len(ranks),
        "gold_misses": primary_count - len(ranks) - len(errors),
        "recall_at_1": sum(rank <= 1 for rank in ranks) / primary_count if primary_count else None,
        "recall_at_3": sum(rank <= 3 for rank in ranks) / primary_count if primary_count else None,
        "recall_at_5": sum(rank <= 5 for rank in ranks) / primary_count if primary_count else None,
        "recall_at_10": sum(rank <= 10 for rank in ranks) / primary_count if primary_count else None,
        "mrr": sum(1 / rank for rank in ranks) / primary_count if primary_count else None,
        "mean_gold_rank_on_hits": statistics.mean(ranks) if ranks else None,
        "hard_negative_in_top5_rate": (
            sum(any(int(rank) <= 5 for rank in (row.get("hard_negative_ranks") or {}).values()) for row in selected)
            / primary_count
            if primary_count else None
        ),
        "scope_violation_rate": (
            sum(int(row.get("scope_violations") or 0) > 0 for row in selected) / primary_count
            if primary_count else None
        ),
        "query_quality": {},
        "by_class": {},
    }
    for row in selected:
        quality = str(row.get("query_quality") or "missing")
        summary["query_quality"][quality] = summary["query_quality"].get(quality, 0) + 1
        category = str(row.get("class") or "unknown")
        category_rows = summary["by_class"].setdefault(category, {"count": 0, "gold_hits": 0, "ranks": []})
        category_rows["count"] += 1
        if row.get("gold_rank"):
            category_rows["gold_hits"] += 1
            category_rows["ranks"].append(row["gold_rank"])
    return summary


def summarize_controls(results: list[dict[str, Any]]) -> dict[str, Any]:
    controls = [row for row in results if row.get("evaluation") != "primary_recall"]
    abstain = [row for row in controls if row.get("evaluation") == "diagnostic_abstain"]
    return {
        "sample_count": len(controls),
        "errors": sum(bool(row.get("error")) for row in controls),
        "abstain_controls": len(abstain),
        "abstain_false_positive": sum(bool(row.get("items")) for row in abstain),
        "results": controls,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    entries = list(manifest.get("primary_cases", [])) + list(manifest.get("diagnostic_controls", []))
    results = []
    for item in entries:
        try:
            payload = request_for_item(args.base_url, item, args.timeout)
            results.append(item_result(item, payload, None))
        except Exception as error:  # one failed case must not hide the rest of the report
            results.append(item_result(item, None, str(error)))

    report = {
        "benchmark_id": manifest.get("benchmark_id"),
        "benchmark_version": manifest.get("version"),
        "base_url": args.base_url,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ranker": manifest.get("primary_ranker"),
        "ai_rerank": manifest.get("ai_rerank"),
        "primary": summarize(results, evaluation="primary_recall"),
        "controls": summarize_controls(results),
        "results": results,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

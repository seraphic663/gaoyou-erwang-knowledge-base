"""Benchmark exact case-set retrieval and API response time for /api/annotation."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import statistics
from http.client import HTTPException
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "research" / "analysis" / "benchmarks" / "annotation-search.v1.json"


def percentile(values: list[float], percentage: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * percentage / 100) - 1))
    return round(ordered[index], 3)


def numeric_ids(values: set[str]) -> list[str]:
    return sorted(values, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))


def fetch_json(
    base_url: str,
    item: dict[str, Any],
    *,
    page_size: int,
    timeout: float,
) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    params: list[tuple[str, str]] = [
        ("q", str(item.get("query") or "")),
        ("page", "1"),
        ("pageSize", str(page_size)),
    ]
    for origin in item.get("origins") or []:
        params.append(("origin", str(origin)))
    for annotator in item.get("annotators") or []:
        params.append(("annotator", str(annotator)))
    url = f"{base_url.rstrip('/')}/api/annotation?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    started = perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
            server_header = response.headers.get("X-API-Time-Ms")
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        HTTPException,
        OSError,
    ) as error:
        elapsed = round((perf_counter() - started) * 1000, 3)
        return None, {"roundtrip_ms": elapsed, "server_ms": None}, f"request_failed:{error}"

    elapsed = round((perf_counter() - started) * 1000, 3)
    try:
        server_ms = float(server_header) if server_header is not None else None
    except ValueError:
        server_ms = None
    if not isinstance(payload, dict):
        return None, {"roundtrip_ms": elapsed, "server_ms": server_ms}, "response_not_object"
    if payload.get("ok") is False:
        return payload, {"roundtrip_ms": elapsed, "server_ms": server_ms}, str(
            payload.get("message") or "annotation_search_not_ok"
        )
    return payload, {"roundtrip_ms": elapsed, "server_ms": server_ms}, None


def evaluate(
    item: dict[str, Any],
    payload: dict[str, Any] | None,
    timing: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    gold = {str(value) for value in item.get("gold_case_ids") or []}
    if error or payload is None:
        return {
            "sample_id": item.get("sample_id"),
            "class": item.get("class"),
            "query": item.get("query"),
            "error": error or "empty_payload",
            "gold_case_ids": numeric_ids(gold),
            "returned_case_ids": [],
            "missing_case_ids": numeric_ids(gold),
            "extra_case_ids": [],
            "duplicate_case_ids": [],
            "exact_set_match": False,
            "precision": 0.0 if gold else None,
            "recall": 0.0 if gold else None,
            "roundtrip_ms": timing.get("roundtrip_ms"),
            "server_ms": timing.get("server_ms"),
        }

    returned_ids = [str(row.get("id")) for row in payload.get("items") or [] if row.get("id") is not None]
    returned = set(returned_ids)
    hits = gold & returned
    missing = gold - returned
    extra = returned - gold
    duplicates = {value for value in returned_ids if returned_ids.count(value) > 1}
    exact = not missing and not extra and not duplicates and len(returned_ids) == len(gold)
    precision = len(hits) / len(returned_ids) if returned_ids else (1.0 if not gold else 0.0)
    recall = len(hits) / len(gold) if gold else (1.0 if not returned_ids else 0.0)
    return {
        "sample_id": item.get("sample_id"),
        "class": item.get("class"),
        "query": item.get("query"),
        "error": None,
        "api_total": payload.get("total"),
        "gold_case_ids": numeric_ids(gold),
        "returned_case_ids": returned_ids,
        "missing_case_ids": numeric_ids(missing),
        "extra_case_ids": numeric_ids(extra),
        "duplicate_case_ids": numeric_ids(duplicates),
        "exact_set_match": exact,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "roundtrip_ms": timing.get("roundtrip_ms"),
        "server_ms": timing.get("server_ms"),
    }


def run_item(
    base_url: str,
    item: dict[str, Any],
    *,
    repeats: int,
    warmup: int,
    page_size: int,
    timeout: float,
) -> dict[str, Any]:
    for _ in range(warmup):
        fetch_json(base_url, item, page_size=page_size, timeout=timeout)

    timings: list[dict[str, Any]] = []
    last_payload: dict[str, Any] | None = None
    last_timing: dict[str, Any] = {}
    request_errors: list[str] = []
    for _ in range(repeats):
        payload, timing, error = fetch_json(base_url, item, page_size=page_size, timeout=timeout)
        timings.append(timing)
        if payload is not None:
            last_payload = payload
            last_timing = timing
        if error:
            request_errors.append(error)

    result = evaluate(
        item,
        last_payload,
        last_timing or (timings[-1] if timings else {}),
        None if last_payload is not None else (request_errors[-1] if request_errors else "no_successful_request"),
    )
    result["request_errors"] = request_errors
    roundtrips = [float(item["roundtrip_ms"]) for item in timings if item.get("roundtrip_ms") is not None]
    server_times = [float(item["server_ms"]) for item in timings if item.get("server_ms") is not None]
    result["timing"] = {
        "repeats": len(timings),
        "roundtrip_ms": {
            "median": round(statistics.median(roundtrips), 3) if roundtrips else None,
            "p95": percentile(roundtrips, 95),
            "min": round(min(roundtrips), 3) if roundtrips else None,
            "max": round(max(roundtrips), 3) if roundtrips else None,
        },
        "server_ms": {
            "median": round(statistics.median(server_times), 3) if server_times else None,
            "p95": percentile(server_times, 95),
            "min": round(min(server_times), 3) if server_times else None,
            "max": round(max(server_times), 3) if server_times else None,
        },
    }
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in results if not row.get("error")]
    exact = [row for row in valid if row.get("exact_set_match")]
    gold_total = sum(len(row.get("gold_case_ids") or []) for row in valid)
    returned_total = sum(len(row.get("returned_case_ids") or []) for row in valid)
    hits_total = sum(
        len(set(row.get("gold_case_ids") or []) & set(row.get("returned_case_ids") or []))
        for row in valid
    )
    roundtrips = [
        float(row["timing"]["roundtrip_ms"]["median"])
        for row in valid
        if row["timing"]["roundtrip_ms"].get("median") is not None
    ]
    server_times = [
        float(row["timing"]["server_ms"]["median"])
        for row in valid
        if row["timing"]["server_ms"].get("median") is not None
    ]
    return {
        "query_count": len(results),
        "successful_queries": len(valid),
        "errors": len(results) - len(valid),
        "request_error_count": sum(len(row.get("request_errors") or []) for row in results),
        "exact_set_accuracy": len(exact) / len(results) if results else None,
        "micro_precision": hits_total / returned_total if returned_total else 1.0,
        "micro_recall": hits_total / gold_total if gold_total else 1.0,
        "missing_total": sum(len(row.get("missing_case_ids") or []) for row in valid),
        "extra_total": sum(len(row.get("extra_case_ids") or []) for row in valid),
        "duplicate_total": sum(len(row.get("duplicate_case_ids") or []) for row in valid),
        "query_median_roundtrip_ms": round(statistics.median(roundtrips), 3) if roundtrips else None,
        "query_p95_roundtrip_ms": percentile(roundtrips, 95),
        "query_median_server_ms": round(statistics.median(server_times), 3) if server_times else None,
        "query_p95_server_ms": percentile(server_times, 95),
        "order_evaluated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = list(manifest.get("queries", []))
    run_args = {
        "repeats": max(1, args.repeats),
        "warmup": max(0, args.warmup),
        "page_size": max(1, args.page_size),
        "timeout": args.timeout,
    }
    if args.workers <= 1:
        results = [run_item(args.base_url, item, **run_args) for item in items]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(run_item, args.base_url, item, **run_args) for item in items]
            results = [future.result() for future in futures]
    report = {
        "benchmark_id": manifest.get("benchmark_id"),
        "benchmark_version": manifest.get("version"),
        "base_url": args.base_url,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest": str(args.manifest),
        "metrics": {
            "accuracy": "exact case-set match; order is ignored",
            "roundtrip_time": "client wall time from HTTP request to JSON response",
            "server_time": "X-API-Time-Ms header measured inside the API route",
        },
        "summary": summarize(results),
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

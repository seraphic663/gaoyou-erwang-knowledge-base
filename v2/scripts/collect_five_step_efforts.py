#!/usr/bin/env python3
"""Collect the public five-step draft API for every reasoning effort.

This runner is read-only with respect to the V2 database.  It calls the
already exposed draft endpoint, saves each returned JSON payload, and records
the prompt/model/effort metadata needed to compare runs later.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


EFFORTS = ("none", "low", "high", "max")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def request_draft(base_url: str, case_id: str, model: str, effort: str, timeout: float) -> tuple[int, dict[str, Any], float]:
    body = json.dumps(
        {"case_id": case_id, "model": model, "reasoning_effort": effort},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v2/five-step-draft",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return int(response.status), payload, time.monotonic() - started
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"ok": False, "message": raw or str(error)}
        return int(error.code), payload, time.monotonic() - started
    except Exception as error:  # Keep the other effort runs independent.
        return 0, {"ok": False, "message": f"{type(error).__name__}: {error}"}, time.monotonic() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--label", required=True, help="Prompt/archive label, for example prompt-v4 or prompt-v5.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    parser.add_argument("--efforts", nargs="+", choices=EFFORTS, default=list(EFFORTS))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for index, effort in enumerate(args.efforts):
        if index:
            time.sleep(max(0.0, args.pause_seconds))
        status, payload, elapsed = request_draft(
            args.base_url,
            args.case_id,
            args.model,
            effort,
            args.timeout,
        )
        output_path = args.output_dir / f"effort-{effort}.json"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(
            {
                "effort": effort,
                "http_status": status,
                "ok": bool(payload.get("ok")) and status == 200,
                "elapsed_seconds": round(elapsed, 3),
                "file": output_path.name,
                "prompt_version": payload.get("prompt_version"),
                "model_requested": payload.get("model_requested", args.model),
                "model_returned": payload.get("model_returned"),
                "reasoning_effort": payload.get("reasoning_effort", effort),
                "generated_at": payload.get("generated_at"),
                "usage": payload.get("usage"),
                "message": payload.get("message") if not payload.get("ok") else None,
            }
        )
        print(json.dumps(records[-1], ensure_ascii=False))

    manifest = {
        "collector": "v2/scripts/collect_five_step_efforts.py",
        "collected_at": utc_now(),
        "base_url": args.base_url,
        "case_id": args.case_id,
        "model": args.model,
        "label": args.label,
        "efforts": list(args.efforts),
        "results": records,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if all(record["ok"] for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())

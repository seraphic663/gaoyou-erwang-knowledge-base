"""Isolated, paired DeepSeek boundary ablation. No request without --execute."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import random
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
INPUT = HERE / "public_inputs.json"
KEY_FILE = HERE.parents[2] / "website" / ".env"
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
REASONING_EFFORT = "high"
MAX_TOKENS = 32768
SEED = 20261025
WORKERS = 2
REPEATS = 2
EXPECTED_ITEMS = 21
TIMEOUT_SECONDS = 120
MAX_TRANSPORT_RETRIES = 2
ROLES = {"正文", "读音", "校记", "出处", "案语", "无法判断"}

SYSTEM_PROMPT = (
    "你是古籍片段的文本边界判读员。只依据本次给出的片段和目标字句判断，不调用外部资料，不补造原文。"
    "这里的“原书正文”专指当前考辨所引用或解释的底本文句，不是片段中所有非注释文字；考辨者自己的论证不能直接算作底本文句。"
    "目标附近的文字可能属于原书正文、读音、校记、出处、案语，也可能无法判断。"
    "排版标记只是线索，不预设所有小字属于同一种角色。"
    "逐项提取与目标判读有关的连续字句，不必穷尽无关内容。"
    "每项 exact_quote 必须从片段中逐字复制一段连续文字；role 只能是“正文”“读音”“校记”“出处”“案语”“无法判断”之一；"
    "explains_quote 填这项文字明确解释、校订或标音的对象原句，若无法确定则填 null；"
    "reason 简要说明可见的判读依据。另在 book_quotes 中列出与目标有关、能可靠作为原书正文引用的底本片段；"
    "可用多个连续原文片段表示被插注隔开的底本文句，不必拼成一整句，也不得补字。"
    "只有考辨叙述或无法确定底本文句时，用空数组，不要凑引文。不得把读音、校记、出处、案语写入 book_quotes。"
    '只返回 JSON 对象，格式为 {"items":[{"exact_quote":"...","role":"...","explains_quote":null,"reason":"..."}],"book_quotes":["..."]}。'
    "不要输出 Markdown 或额外说明。"
)
USER_TEMPLATE = (
    "请判读下列片段中与目标字句有关的文字边界及归属。\n"
    "目标字句：{target_quote_json}\n"
    "片段：{text_json}"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prompt_sha256() -> str:
    return sha256((SYSTEM_PROMPT + "\0" + USER_TEMPLATE).encode("utf-8"))


def strip_small_tags(text: str) -> str:
    return text.replace("<small>", "").replace("</small>", "")


def validate_tags(text: str, case_id: str) -> None:
    depth = 0
    seen = False
    for match in re.finditer(r"<small>|</small>", text):
        if match.group() == "<small>":
            depth += 1
            seen = True
        else:
            depth -= 1
        if depth < 0 or depth > 1:
            raise ValueError(f"{case_id}: malformed small-tag nesting")
    if not seen or depth != 0:
        raise ValueError(f"{case_id}: missing or unbalanced small tags")


def load_inputs(path: Path) -> tuple[list[dict[str, str]], bytes]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict) or set(payload) != {"items"} or not isinstance(payload["items"], list):
        raise ValueError("input must be exactly an object with an items array")
    items: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, candidate in enumerate(payload["items"]):
        if not isinstance(candidate, dict) or set(candidate) != {"id", "text", "target_quote"}:
            raise ValueError(f"item {index}: only id, text, target_quote are accepted")
        if any(not isinstance(candidate[key], str) or not candidate[key] for key in ("id", "text", "target_quote")):
            raise ValueError(f"item {index}: all three fields must be nonempty strings")
        if candidate["id"] in seen_ids:
            raise ValueError(f"duplicate id: {candidate['id']}")
        seen_ids.add(candidate["id"])
        validate_tags(candidate["text"], candidate["id"])
        if candidate["target_quote"] not in strip_small_tags(candidate["text"]):
            raise ValueError(f"{candidate['id']}: target_quote absent from untagged text")
        items.append({key: candidate[key] for key in ("id", "text", "target_quote")})
    return items, raw


def build_plan(items: list[dict[str, str]]) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    plan = []
    for repeat in range(1, REPEATS + 1):
        shuffled = items.copy()
        rng.shuffle(shuffled)
        for item in shuffled:
            conditions = ["tagged", "untagged"]
            if rng.randrange(2):
                conditions.reverse()
            for condition in conditions:
                plan.append({"plan_index": len(plan) + 1, "repeat": repeat, "id": item["id"], "condition": condition})
    return plan


def make_request(item: dict[str, str], condition: str) -> tuple[dict[str, Any], str]:
    if condition not in {"tagged", "untagged"}:
        raise ValueError(f"unknown condition: {condition}")
    text = item["text"] if condition == "tagged" else strip_small_tags(item["text"])
    if condition == "untagged" and text != item["text"].replace("<small>", "").replace("</small>", ""):
        raise ValueError("condition changed more than small tags")
    user_prompt = USER_TEMPLATE.format(
        target_quote_json=json.dumps(item["target_quote"], ensure_ascii=False),
        text_json=json.dumps(text, ensure_ascii=False),
    )
    return {
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }, text


def read_key() -> str:
    import os

    names = ("DEEPSEEK_ANALYSIS_API_KEY", "DEEPSEEK_API_KEY_BACKUP", "DEEPSEEK_API_KEY")
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if KEY_FILE.is_file():
        values = {}
        for line in KEY_FILE.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"^\s*(DEEPSEEK_ANALYSIS_API_KEY|DEEPSEEK_API_KEY_BACKUP|DEEPSEEK_API_KEY)\s*=\s*(.*)$", line)
            if match:
                value = match.group(2).strip().strip('"\'')
                values[match.group(1)] = value
        for name in names:
            if values.get(name):
                return values[name]
    raise RuntimeError("DeepSeek API key unavailable")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def validate_output(payload: Any, source_text: str) -> list[str]:
    issues = []
    if not isinstance(payload, dict) or set(payload) != {"items", "book_quotes"}:
        return ["top-level JSON must contain exactly items and book_quotes"]
    if not isinstance(payload["items"], list):
        issues.append("items is not an array")
    else:
        for index, item in enumerate(payload["items"]):
            if not isinstance(item, dict) or set(item) != {"exact_quote", "role", "explains_quote", "reason"}:
                issues.append(f"items[{index}] has wrong fields")
                continue
            quote = item["exact_quote"]
            if not isinstance(quote, str) or not quote or quote not in source_text:
                issues.append(f"items[{index}].exact_quote is not an exact source substring")
            if not isinstance(item["role"], str) or item["role"] not in ROLES:
                issues.append(f"items[{index}].role is not allowed")
            explains = item["explains_quote"]
            if explains is not None and (not isinstance(explains, str) or not explains or explains not in source_text):
                issues.append(f"items[{index}].explains_quote is not an exact source substring or null")
            if not isinstance(item["reason"], str) or not item["reason"]:
                issues.append(f"items[{index}].reason is empty")
    if not isinstance(payload["book_quotes"], list):
        issues.append("book_quotes is not an array")
    else:
        for index, quote in enumerate(payload["book_quotes"]):
            if not isinstance(quote, str) or not quote or quote not in source_text:
                issues.append(f"book_quotes[{index}] is not an exact source substring")
    return issues


def redact(value: str, key: str) -> str:
    return value.replace(key, "[REDACTED]") if key else value


def request_once(body: dict[str, Any], key: str) -> tuple[int | None, str | None, str | None, bool]:
    """Returns HTTP status, raw response, error, and whether transport retry is allowed."""
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read().decode("utf-8", errors="replace"), None, False
    except urllib.error.HTTPError as exc:
        response = exc.read().decode("utf-8", errors="replace")
        return exc.code, response, f"HTTP {exc.code}", False
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
        return None, None, f"transport: {type(exc).__name__}: {exc}", True


def parse_response(status: int | None, response_text: str | None, source_text: str) -> tuple[str, str | None, Any, Any, list[str]]:
    if status is None:
        return "transport_error", None, None, None, []
    if not (200 <= status < 300):
        return "http_error", None, None, None, []
    try:
        response = json.loads(response_text or "")
    except json.JSONDecodeError as exc:
        return "invalid_api_json", None, None, None, [str(exc)]
    if not isinstance(response, dict):
        return "invalid_api_json", None, None, None, ["API response is not an object"]
    returned_model = response.get("model")
    usage = response.get("usage")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "invalid_output", returned_model, usage, None, ["missing first choice"]
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        return "truncated", returned_model, usage, None, ["finish_reason=length"]
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        return "invalid_output", returned_model, usage, None, ["empty content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        return "invalid_output", returned_model, usage, None, [f"content JSON: {exc}"]
    issues = validate_output(parsed, source_text)
    return ("valid" if not issues else "invalid_output"), returned_model, usage, parsed, issues


def blocking_http_error(status: int | None, response_text: str | None) -> str | None:
    """Classify provider configuration failures before scheduling more work."""
    if status is None or 200 <= status < 300:
        return None
    if status in {401, 403}:
        return "authentication_or_permission"
    if status == 402:
        return "billing"
    text = response_text or ""
    try:
        parsed = json.loads(text)
        detail = parsed.get("error", {}) if isinstance(parsed, dict) else {}
        if isinstance(detail, dict):
            text = " ".join(str(detail.get(key, "")) for key in ("code", "type", "message"))
    except json.JSONDecodeError:
        pass
    lowered = text.lower()
    if any(term in lowered for term in ("insufficient balance", "insufficient funds", "insufficient credits", "billing", "payment required", "余额不足")):
        return "billing"
    if ("model" in lowered or "模型" in lowered) and any(
        term in lowered for term in ("not support", "unsupported", "not found", "does not exist", "invalid", "unavailable", "不可用", "不支持")
    ):
        return "model_unavailable"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate inputs and print frozen prompt hash; no API")
    parser.add_argument("--execute", action="store_true", help="Send all planned API requests")
    parser.add_argument("--frozen-prompt-sha256", help="Must match the reviewed prompt hash for --execute")
    args = parser.parse_args()
    if args.check == args.execute:
        parser.error("select exactly one of --check or --execute")
    items, raw_input = load_inputs(INPUT)
    plan = build_plan(items)
    prompt_hash = prompt_sha256()
    if args.check:
        print(json.dumps({"items": len(items), "requests": len(plan), "input_sha256": sha256(raw_input), "prompt_sha256": prompt_hash}, ensure_ascii=False))
        return 0
    if len(items) != EXPECTED_ITEMS:
        raise ValueError(f"expected exactly {EXPECTED_ITEMS} items for the frozen run")
    if args.frozen_prompt_sha256 != prompt_hash:
        raise ValueError("--frozen-prompt-sha256 does not match this runner")
    key = read_key()
    out = HERE / "runs" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=False)
    metadata = {
        "created_utc": utc_now(),
        "input_path": str(INPUT.resolve()),
        "input_sha256": sha256(raw_input),
        "prompt_sha256": prompt_hash,
        "prompt_hash_encoding": "SHA-256 of UTF-8 SYSTEM_PROMPT + NUL + USER_TEMPLATE",
        "api_url": API_URL,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "max_tokens": MAX_TOKENS,
        "seed": SEED,
        "workers": WORKERS,
        "repeats": REPEATS,
        "transport_retries": MAX_TRANSPORT_RETRIES,
        "plan": plan,
    }
    (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log_lock = threading.Lock()
    log_path = out / "attempts.jsonl"
    lookup = {item["id"]: item for item in items}

    def run_job(job: dict[str, Any]) -> tuple[str, str | None]:
        body, source_text = make_request(lookup[job["id"]], job["condition"])
        for attempt in range(1, MAX_TRANSPORT_RETRIES + 2):
            started = utc_now()
            start_clock = time.monotonic()
            status, response_text, error, retryable = request_once(body, key)
            ended = utc_now()
            outcome, returned_model, usage, parsed, issues = parse_response(status, response_text, source_text)
            blocker = blocking_http_error(status, response_text)
            entry = {
                **job,
                "attempt": attempt,
                "started_utc": started,
                "ended_utc": ended,
                "elapsed_seconds": round(time.monotonic() - start_clock, 3),
                "request_url": API_URL,
                "request": body,
                "http_status": status,
                "response": redact(response_text, key) if response_text is not None else None,
                "model_returned": returned_model,
                "usage": usage,
                "parsed_output": parsed,
                "outcome": outcome,
                "blocking_http_error": blocker,
                "error": redact(error, key) if error else None,
                "format_issues": issues,
                "will_retry": bool(retryable and attempt <= MAX_TRANSPORT_RETRIES),
            }
            with log_lock:
                with log_path.open("a", encoding="utf-8", newline="\n") as log:
                    log.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if not retryable or attempt > MAX_TRANSPORT_RETRIES:
                return outcome, blocker
            time.sleep(attempt)
        raise AssertionError("unreachable")

    outcomes: dict[str, int] = {}
    blocker_streak = 0
    stopped_for: str | None = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        next_index = 0
        pending: dict[concurrent.futures.Future[tuple[str, str | None]], int] = {}
        while next_index < len(plan) or pending:
            capacity = WORKERS if blocker_streak == 0 else 1
            while next_index < len(plan) and len(pending) < capacity and stopped_for is None:
                future = executor.submit(run_job, plan[next_index])
                pending[future] = next_index
                next_index += 1
            if not pending:
                break
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in sorted(done, key=lambda item: pending[item]):
                pending.pop(future)
                outcome, blocker = future.result()
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
                if blocker:
                    blocker_streak += 1
                    if blocker_streak >= 2:
                        stopped_for = blocker
                else:
                    blocker_streak = 0
            if stopped_for is not None:
                for future in concurrent.futures.as_completed(pending):
                    outcome, _ = future.result()
                    outcomes[outcome] = outcomes.get(outcome, 0) + 1
                pending.clear()
                break
    summary = {
        "planned": len(plan),
        "completed": sum(outcomes.values()),
        "unsent": len(plan) - sum(outcomes.values()),
        "outcomes": outcomes,
        "stopped_for_consecutive_blocking_http_errors": stopped_for,
        "results_directory": str(out.resolve()),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if sum(outcomes.values()) == len(plan) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"experiment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

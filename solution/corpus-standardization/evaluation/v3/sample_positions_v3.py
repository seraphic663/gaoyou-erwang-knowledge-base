"""Create source-only, fixed-seed positions for the independent V3 review.

Offsets are Python Unicode code-point indexes into raw UTF-8-decoded bytes.
Decoding with bytes.decode preserves CRLF and counts a leading BOM.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path


SEED = 20261025
MIN_OLD_DISTANCE = 5000
WINDOW = 240
ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).with_name("positions.json")
PRIOR_POSITIONS = ROOT / "solution" / "corpus-standardization" / "evaluation" / "positions.json"

WANG_FILES = [
    ROOT / "data" / "A-原著原典" / "读书杂志_王念孙.md",
    ROOT / "data" / "A-原著原典" / "广雅疏证_王念孙.md",
    ROOT / "data" / "A-原著原典" / "经传释词_王引之.md",
    ROOT / "data" / "A-原著原典" / "经义述闻_王引之.md",
]
EXTERNAL_BUCKETS = [
    ("高频", "external_high"),
    ("中频", "external_mid"),
    ("低频", "external_low"),
]

PUNCTUATION = re.compile(r"[，。！？；：、,.!?;:]")
PARAGRAPH_BREAK = re.compile(r"(?:\r?\n[ \t]*){2,}")
MARKDOWN_HEADING = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+\S")
BRACKET_MARKER = re.compile(r"[【】〔〕（）()]")
INLINE_NOTE_TAG = re.compile(r"</?small\b", re.IGNORECASE)
HTML_COMMENT = re.compile(r"<!--|-->")


def decode_source(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def body_start(text: str) -> int:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return 0

    offset = len(lines[0])
    for line in lines[1:]:
        offset += len(line)
        if line.strip() == "---":
            return offset
    return 0


def allowed_ranges(start: int, end: int, old_anchors: list[int]) -> list[tuple[int, int]]:
    """Return half-open code-point ranges at least 5000 cp from old anchors."""
    blocked: list[tuple[int, int]] = []
    for anchor in old_anchors:
        left = max(start, anchor - (MIN_OLD_DISTANCE - 1))
        right = min(end, anchor + MIN_OLD_DISTANCE)
        if left < right:
            blocked.append((left, right))
    blocked.sort()

    merged: list[tuple[int, int]] = []
    for left, right in blocked:
        if not merged or left > merged[-1][1]:
            merged.append((left, right))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))

    ranges: list[tuple[int, int]] = []
    cursor = start
    for left, right in merged:
        if cursor < left:
            ranges.append((cursor, left))
        cursor = max(cursor, right)
    if cursor < end:
        ranges.append((cursor, end))
    return ranges


def choose_anchor(rng: random.Random, ranges: list[tuple[int, int]]) -> int:
    total = sum(right - left for left, right in ranges)
    if total <= 0:
        raise ValueError("No source offsets remain after excluding prior positions")
    rank = rng.randrange(total)
    for left, right in ranges:
        width = right - left
        if rank < width:
            return left + rank
        rank -= width
    raise AssertionError("Offset selection fell outside allowed ranges")


def local_block(text: str, start: int, anchor: int) -> str:
    body = text[start:]
    relative_anchor = anchor - start
    previous_end = 0
    next_start = len(body)

    for match in PARAGRAPH_BREAK.finditer(body):
        if match.end() <= relative_anchor:
            previous_end = match.end()
        elif match.start() >= relative_anchor:
            next_start = match.start()
            break
        elif match.start() <= relative_anchor < match.end():
            left = body[previous_end:match.start()].strip()
            right_match = PARAGRAPH_BREAK.search(body, match.end())
            right_end = right_match.start() if right_match else len(body)
            right = body[match.end():right_end].strip()
            return left if len(left) >= len(right) else right

    return body[previous_end:next_start].strip()


def describe_form(text: str, start: int, anchor: int) -> str:
    block = local_block(text, start, anchor)
    window = text[max(start, anchor - WINDOW):min(len(text), anchor + WINDOW)]

    if not block:
        block_shape = "空白间隔"
    elif len(block) <= 120:
        block_shape = f"短块({len(block)}cp)"
    elif len(block) < 500:
        block_shape = f"中块({len(block)}cp)"
    else:
        block_shape = f"长块({len(block)}cp)"

    punctuation = "有句读标点" if PUNCTUATION.search(block or window) else "无句读标点"
    heading = "近Markdown条头" if MARKDOWN_HEADING.search(window) else "未见近Markdown条头"
    bracket = "见括注符号" if BRACKET_MARKER.search(window) else "未见括注符号"
    inline_tag = "见行内注释标签" if INLINE_NOTE_TAG.search(window) else "未见行内注释标签"
    comment = "见HTML注释标记" if HTML_COMMENT.search(window) else "未见HTML注释标记"
    return "；".join((punctuation, block_shape, heading, bracket, inline_tag, comment))


def load_old_positions() -> dict[str, list[int]]:
    payload = json.loads(PRIOR_POSITIONS.read_text(encoding="utf-8"))
    old: dict[str, list[int]] = defaultdict(list)
    for item in payload["items"]:
        old[item["path"]].append(int(item["anchor"]))
    return old


def add_item(
    items: list[dict[str, object]],
    path: Path,
    collection: str,
    anchor: int,
    text: str,
    start: int,
) -> None:
    items.append(
        {
            "id": f"T{len(items) + 1:02d}",
            "path": path.relative_to(ROOT).as_posix(),
            "anchor": anchor,
            "collection": collection,
            "form": describe_form(text, start, anchor),
        }
    )


def main() -> None:
    rng = random.Random(SEED)
    old_positions = load_old_positions()
    items: list[dict[str, object]] = []
    blocked_offsets_by_path: dict[str, int] = {}

    for path in WANG_FILES:
        if not path.is_file():
            raise FileNotFoundError(path)
        text = decode_source(path)
        start = body_start(text)
        ranges = allowed_ranges(start, len(text), old_positions.get(path.relative_to(ROOT).as_posix(), []))
        if not ranges:
            raise ValueError(f"No eligible text remains in {path}")
        blocked_offsets_by_path[path.relative_to(ROOT).as_posix()] = (len(text) - start) - sum(
            right - left for left, right in ranges
        )
        for anchor in sorted(choose_anchor(rng, ranges) for _ in range(2)):
            add_item(items, path, "wang", anchor, text, start)

    for folder, collection in EXTERNAL_BUCKETS:
        directory = ROOT / "data" / "daizhigev20" / folder
        files = sorted(directory.rglob("*.md"), key=lambda p: p.as_posix())
        eligible_files: list[Path] = []
        for path in files:
            key = path.relative_to(ROOT).as_posix()
            text = decode_source(path)
            start = body_start(text)
            if allowed_ranges(start, len(text), old_positions.get(key, [])):
                eligible_files.append(path)
        if len(eligible_files) < 8:
            raise ValueError(f"Need 8 eligible Markdown files in {directory}; found {len(eligible_files)}")

        for path in rng.sample(eligible_files, 8):
            key = path.relative_to(ROOT).as_posix()
            text = decode_source(path)
            start = body_start(text)
            ranges = allowed_ranges(start, len(text), old_positions.get(key, []))
            blocked_offsets_by_path[key] = (len(text) - start) - sum(right - left for left, right in ranges)
            add_item(items, path, collection, choose_anchor(rng, ranges), text, start)

    if len(items) != 32:
        raise AssertionError(f"Expected 32 positions, got {len(items)}")

    collection_counts = Counter(item["collection"] for item in items)
    if collection_counts != Counter({"wang": 8, "external_high": 8, "external_mid": 8, "external_low": 8}):
        raise AssertionError(f"Unexpected collection counts: {collection_counts}")

    wang_counts = Counter(item["path"] for item in items if item["collection"] == "wang")
    if any(count != 2 for count in wang_counts.values()) or len(wang_counts) != 4:
        raise AssertionError("Expected two positions from each of the four Wang source files")

    external_paths_by_collection: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if item["collection"] != "wang":
            external_paths_by_collection[str(item["collection"])].add(str(item["path"]))
    if any(len(paths) != 8 for paths in external_paths_by_collection.values()):
        raise AssertionError("Each external tier must use eight different files")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"seed": SEED, "items": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    form_counts = Counter()
    for item in items:
        for label in str(item["form"]).split("；"):
            form_counts[label.split("(", 1)[0]] += 1
    print(f"Wrote {len(items)} positions to {OUTPUT}")
    print("By collection:", dict(collection_counts))
    print("Distinct source files:", len({str(item['path']) for item in items}))
    print("Prior-proximity-excluded codepoints across sampled files:", sum(blocked_offsets_by_path.values()))
    print("Observed source forms:", dict(form_counts))


if __name__ == "__main__":
    main()

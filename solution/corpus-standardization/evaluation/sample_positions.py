"""Create fixed-seed, source-only positions for blind segmentation review.

Offsets are Python Unicode code-point indexes into bytes.decode("utf-8") of the
whole original file. They therefore count a leading BOM and preserve CRLF.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path


SEED = 20261024
ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).with_name("positions.json")
WINDOW = 240

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
    """Decode the raw source without newline conversion or BOM removal."""
    return path.read_bytes().decode("utf-8")


def body_start(text: str) -> int:
    """Skip a leading Markdown YAML front matter block, if it is closed."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return 0

    offset = len(lines[0])
    for line in lines[1:]:
        offset += len(line)
        if line.strip() == "---":
            return offset
    return 0


def local_block(text: str, start: int, anchor: int) -> str:
    """Return the blank-line-delimited source block containing the anchor."""
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
            "id": f"S{len(items) + 1:02d}",
            "path": path.relative_to(ROOT).as_posix(),
            "anchor": anchor,
            "collection": collection,
            "form": describe_form(text, start, anchor),
        }
    )


def main() -> None:
    rng = random.Random(SEED)
    items: list[dict[str, object]] = []

    for path in WANG_FILES:
        if not path.is_file():
            raise FileNotFoundError(path)
        text = decode_source(path)
        start = body_start(text)
        if len(text) - start < 2:
            raise ValueError(f"No usable body text in {path}")
        for anchor in sorted(rng.sample(range(start, len(text)), 2)):
            add_item(items, path, "wang", anchor, text, start)

    for folder, collection in EXTERNAL_BUCKETS:
        directory = ROOT / "data" / "daizhigev20" / folder
        files = sorted(directory.rglob("*.md"), key=lambda p: p.as_posix())
        if len(files) < 8:
            raise ValueError(f"Need at least 8 Markdown files in {directory}")
        for path in rng.sample(files, 8):
            text = decode_source(path)
            start = body_start(text)
            if len(text) <= start:
                raise ValueError(f"No usable body text in {path}")
            anchor = rng.randrange(start, len(text))
            add_item(items, path, collection, anchor, text, start)

    if len(items) != 32:
        raise AssertionError(f"Expected 32 positions, got {len(items)}")

    path_counts = Counter(item["path"] for item in items)
    if max(path_counts.values()) > 2:
        raise AssertionError("More than two positions were selected from a file")

    payload = {"seed": SEED, "items": items}
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    collection_counts = Counter(item["collection"] for item in items)
    form_counts = Counter()
    for item in items:
        for label in item["form"].split("；"):
            form_counts[label.split("(", 1)[0]] += 1

    print(f"Wrote {len(items)} positions to {OUTPUT}")
    print("By collection:", dict(collection_counts))
    print("Observed source forms:", dict(form_counts))


if __name__ == "__main__":
    main()

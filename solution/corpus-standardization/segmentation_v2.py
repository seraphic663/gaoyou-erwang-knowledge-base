"""Conservative, source-coordinate structural segmentation of classical texts.

The rules identify visible layout, not an edition's authoritative hierarchy.
Every returned span refers to the unchanged decoded source text.
"""

from __future__ import annotations

import hashlib
import bisect
import re
from typing import Any


TARGET_SIZE = 600
MAX_SIZE = 1200
_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n|$)")
_MARKDOWN = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")
_SYMBOL = re.compile(r"^([●○◇])[ \t]*(.{1,100}?)\s*$")
_VOLUME = re.compile(r"^(?:[\u4e00-\u9fff]{0,12})[卷巻][一二三四五六七八九十百千〇零两兩0-9０-９]+(?:[上下中])?(?:[ \t　]+[^。！？；]{0,18})?$|^第[一二三四五六七八九十百千〇零两兩0-9０-９]+(?:[一二三四五六七八九十百千〇零两兩0-9０-９]+)?部$")
_ARTICLE = re.compile(r"^.{1,40}?[篇章]第[一二三四五六七八九十百千〇零两兩0-9０-９]+(?:【[^】]{0,200}】)?$")
_SENTENCE = re.compile(r"[。！？；](?:[”’」』】》])*|[\r\n]+")
_NEWLINE = r"(?:\r\n|\r(?!\n)|(?<!\r)\n)"
_PARAGRAPH = re.compile(_NEWLINE + r"[ \t　]*" + _NEWLINE + r"+")
_NOTE_MARKER = re.compile(r"<small>|</small>|[【】（）\[\]()]")
_OPEN = {"【": "】", "（": "）", "[": "]", "(": ")"}


def _lines(raw: str, start: int) -> list[tuple[int, int, str]]:
    result = []
    for match in _LINE.finditer(raw, start):
        if match.start() == match.end():
            continue
        line = match.group()
        visible = line.rstrip("\r\n")
        result.append((match.start(), match.start() + len(visible), visible))
    return result


def _note_ranges(raw: str, start: int) -> list[tuple[int, int]]:
    """Paired inline note candidates, including multiline and nested spans."""
    stack: list[tuple[str, int]] = []
    paired: list[tuple[int, int]] = []
    for marker in _NOTE_MARKER.finditer(raw, start):
        value = marker.group()
        if value in _OPEN:
            stack.append((_OPEN[value], marker.start()))
        elif value == "<small>":
            stack.append(("</small>", marker.start()))
        else:
            matching = next((index for index in range(len(stack) - 1, -1, -1)
                             if stack[index][0] == value), None)
            if matching is not None:
                opening = stack[matching][1]
                del stack[matching:]
                paired.append((opening, marker.end()))
    spans: list[tuple[int, int]] = []
    for opening, closing in sorted(paired):
        if spans and opening < spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], closing))
        else:
            spans.append((opening, closing))
    return spans


def _heading(lines: list[tuple[int, int, str]], index: int,
             next_text: str) -> dict[str, Any] | None:
    start, end, original = lines[index]
    text = original.strip()
    if not text:
        return None
    markdown = _MARKDOWN.fullmatch(text)
    if markdown:
        depth = len(markdown.group(1))
        return {"level": min(depth, 4), "kind": "markdown", "title": markdown.group(2),
                "start_cp": start, "end_cp": end, "confidence": "explicit"}
    symbol = _SYMBOL.fullmatch(text)
    if symbol:
        mark = symbol.group(1)
        return {"level": {"●": 2, "○": 3, "◇": 4}[mark], "kind": "symbol",
                "title": symbol.group(2), "start_cp": start, "end_cp": end,
                "confidence": "explicit"}
    if len(text) <= 48 and _VOLUME.fullmatch(text):
        return {"level": 2, "kind": "volume", "title": text, "start_cp": start,
                "end_cp": end, "confidence": "pattern"}
    if _ARTICLE.fullmatch(text):
        return {"level": 3, "kind": "article", "title": text, "start_cp": start,
                "end_cp": end, "confidence": "pattern"}
    # A headword directly followed by an explicit explanation label is a
    # general layout cue; neither spelling nor source title is special-cased.
    if (len(text) <= 32 and not re.search(r"[。！？；：:]", text)
            and next_text.startswith("注解：")):
        return {"level": 3, "kind": "headword", "title": text, "start_cp": start,
                "end_cp": end, "confidence": "pattern"}
    if (len(text) <= 24 and re.fullmatch(r"[^\s。！？；：:，,、<>【】（）\[\]()]{1,12}(?:【[^】]{1,20}】)?", text)
            and next_text.startswith(("【", "（", "[", "<small>"))):
        return {"level": 3, "kind": "headword", "title": text, "start_cp": start,
                "end_cp": end, "confidence": "candidate"}
    # A short isolated line followed by prose/verse may be a title. Mark it
    # as a candidate, because title pages and tables of contents vary.
    preceding_blank = index > 0 and not lines[index - 1][2].strip()
    if (preceding_blank and 2 <= len(text) <= 32
            and not re.search(r"[。！？；：:，,、【】<>]", text)
            and next_text and bool(re.search(r"[。！？；，,]", next_text))):
        return {"level": 3, "kind": "plain_title", "title": text, "start_cp": start,
                "end_cp": end, "confidence": "candidate"}
    return None


def _inside_note(note_spans: list[tuple[int, int]], position: int) -> bool:
    """Whether a cut lies in a paired note-like span; no author is inferred."""
    index = bisect.bisect_left(note_spans, (position, -1)) - 1
    return index >= 0 and note_spans[index][0] < position < note_spans[index][1]


def _cuts(raw: str, start: int, end: int, target: int, maximum: int,
          note_spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Use natural boundaries, then a fixed fallback only for boundaryless runs."""
    if end - start <= maximum:
        return [(start, end)]
    text = raw[start:end]
    choices: list[tuple[int, int]] = []
    for pattern, priority in ((_PARAGRAPH, 0), (_SENTENCE, 1)):
        for match in pattern.finditer(text):
            position = start + match.end()
            if start < position < end and not _inside_note(note_spans, position):
                choices.append((position, priority))
    # Single line endings matter in verse and dictionaries without blank lines.
    for match in re.finditer(r"\r\n|\r|\n", text):
        position = start + match.end()
        if start < position < end and not _inside_note(note_spans, position):
            choices.append((position, 2))
    choices = sorted(set(choices))
    positions = [position for position, _ in choices]
    useful = {position for position, _ in choices if position >= start + target // 2}
    if len(useful) <= 1:
        # One isolated line break is not enough structure for a long run.
        step = target - min(100, target // 6)
        return [(position, min(position + target, end))
                for position in range(start, end, step)
                if position < end and (position == start or end - position > 100)]
    result: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > maximum:
        minimum = cursor + min(target // 2, maximum // 2)
        maximum_here = cursor + maximum
        candidates = choices[bisect.bisect_left(positions, minimum):
                             bisect.bisect_right(positions, maximum_here)]
        if candidates:
            position, _ = min(candidates, key=lambda item: (item[1], abs(item[0] - (cursor + target))))
        else:
            # Keep this one fallback local to a long, unstructured stretch.
            position = cursor + min(target, maximum)
        result.append((cursor, position))
        cursor = position
    if cursor < end:
        result.append((cursor, end))
    return result


def segment_source(raw: str, body_start: int, source_id: str,
                   target: int = TARGET_SIZE, maximum: int = MAX_SIZE) -> list[dict[str, Any]]:
    """Return ordered, gap-free spans and their tentative source hierarchy."""
    if not 0 <= body_start <= len(raw) or not 0 < target <= maximum:
        raise ValueError("Invalid source range or segment size")
    if body_start == len(raw):
        return []
    lines = _lines(raw, body_start)
    note_spans_all = _note_ranges(raw, body_start)
    note_starts = [left for left, _ in note_spans_all]
    next_nonempty = [""] * len(lines)
    following = ""
    for index in range(len(lines) - 1, -1, -1):
        next_nonempty[index] = following
        if lines[index][2].strip():
            following = lines[index][2].strip()
    headings = [(index, found) for index in range(len(lines))
                if not _inside_note(note_spans_all, lines[index][0])
                and (found := _heading(lines, index, next_nonempty[index])) is not None]
    events: list[tuple[int, dict[str, Any] | None, list[dict[str, Any]]]] = []
    stack: list[dict[str, Any]] = []
    for _, heading in headings:
        while stack and stack[-1]["level"] >= heading["level"]:
            stack.pop()
        stack.append(heading)
        events.append((heading["start_cp"], heading, list(stack)))
    regions: list[tuple[int, int, dict[str, Any] | None, list[dict[str, Any]]]] = []
    if not events:
        regions.append((body_start, len(raw), None, []))
    else:
        if body_start < events[0][0]:
            regions.append((body_start, events[0][0], None, []))
        for index, (start, heading, path) in enumerate(events):
            end = events[index + 1][0] if index + 1 < len(events) else len(raw)
            regions.append((start, end, heading, path))
    output: list[dict[str, Any]] = []
    for region_start, region_end, heading, path in regions:
        # Unheaded runs are independent paragraphs, including their separators.
        parent_ranges = [(region_start, region_end)] if heading else []
        if heading is None:
            cursor = region_start
            for match in _PARAGRAPH.finditer(raw, region_start, region_end):
                if (_inside_note(note_spans_all, match.start())
                        or _inside_note(note_spans_all, match.end())):
                    continue
                boundary = match.end()
                if cursor < boundary:
                    parent_ranges.append((cursor, boundary))
                cursor = boundary
            if cursor < region_end:
                parent_ranges.append((cursor, region_end))
            joined: list[tuple[int, int]] = []
            for start, end in parent_ranges:
                paragraph = raw[start:end].strip()
                note_only = (paragraph.startswith("<small>") and paragraph.endswith("</small>")
                             or paragraph.startswith("【") and paragraph.endswith("】")
                             or paragraph.startswith("（") and paragraph.endswith("）"))
                if note_only and joined:
                    previous_start, _ = joined.pop()
                    joined.append((previous_start, end))
                else:
                    joined.append((start, end))
            parent_ranges = joined
        for parent_start, parent_end in parent_ranges:
            if parent_start == parent_end:
                continue
            note_spans = [span for span in note_spans_all[
                bisect.bisect_left(note_starts, parent_start):
                bisect.bisect_left(note_starts, parent_end)]
                if span[1] <= parent_end]
            pieces = _cuts(raw, parent_start, parent_end, target, maximum, note_spans)
            parent_id = "par_" + hashlib.sha256(f"{source_id}:{parent_start}:{parent_end}".encode()).hexdigest()
            heading_path = [{key: item[key] for key in ("kind", "title", "start_cp", "end_cp", "confidence")}
                            for item in path]
            toc_candidate = bool(heading and not raw[heading["end_cp"]:parent_end].strip())
            for part_index, (start, end) in enumerate(pieces, 1):
                output.append({
                    "start_cp": start, "end_cp": end,
                    "role": ("entry" if heading and heading["level"] >= 3 else
                             "chapter" if heading else "paragraph"),
                    "structure": {
                        "parent_id": parent_id, "parent_start_cp": parent_start,
                        "parent_end_cp": parent_end, "heading_path": heading_path,
                        "part_index": part_index, "part_count": len(pieces),
                        "continued": part_index > 1, "continues_next": part_index < len(pieces),
                        "boundary_kind": heading["kind"] if heading else "paragraph",
                        "toc_candidate": toc_candidate,
                        "note_continued_from_previous": _inside_note(note_spans, start) if part_index > 1 else False,
                        "note_continues_next": _inside_note(note_spans, end) if part_index < len(pieces) else False,
                    },
                })
    return output

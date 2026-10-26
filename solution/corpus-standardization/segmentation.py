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
_SYMBOL = re.compile(r"^([●○◇◎※△])[ \t]*(.{1,100}?)\s*$")
_NUM = r"[一二三四五六七八九十百千〇零两兩0-9０-９]+"
_VOLUME = re.compile(
    rf"^(?:[\u4e00-\u9fff]{{0,12}})[卷巻](?:之)?{_NUM}(?:[上下中])?"
    r"(?:[ \t　]+[^。！？；]{0,24})?$|" + rf"^第{_NUM}部$"
)
_ARTICLE = re.compile(
    rf"^.{{0,40}}?(?:篇|章|列傳|列传)第{_NUM}(?:【[^】]{{0,200}}】)?$|"
    rf"^第{_NUM}(?:篇|章|列傳|列传)$"
)
_CLOSER = re.compile(rf"^(?:右|以上|已上)(?:[本此前上]?)?(?:章|篇|卷)(?:第?{_NUM})?(?:竟|終|终|畢|毕)?$")
_TOC_LABEL = re.compile(r"^.{0,24}(?:目錄|目录|目録)$")
_APPARATUS = re.compile(r"^(?:脚注|註釋|注释|校勘記|校勘记|校記|校记|附註|附注)$")
_PARATEXT = re.compile(r"^.{0,24}(?:序|敘|叙|跋|後序|后序|後記|后记|出版説明|出版说明)$|^跋跋$")
_EXPLANATION = re.compile(
    r"^(?:(?:[\u4e00-\u9fff]{1,4})?(?:謹案|谨案|案|按|曰|云)|"
    r"注解|解曰|釋曰|释曰|言|謂|谓)(?:[:：，,]|(?=[\u4e00-\u9fff]))"
)
_CITATION = re.compile(r"(?:《[^》]{1,40}》.{0,16}?[曰云]|[「『“][^」』”]{1,100}[」』”])")
_SENTENCE = re.compile(r"[。！？；](?:[”’」』】》])*|[\r\n]+")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
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
    symbol = _SYMBOL.fullmatch(text)
    if markdown:
        title, level, kind, confidence = markdown.group(2), min(len(markdown.group(1)), 4), "markdown", "explicit"
    elif symbol:
        title = symbol.group(2)
        level, kind, confidence = {"●": 2, "◎": 2, "○": 3, "◇": 4, "※": 4, "△": 4}[symbol.group(1)], "symbol", "explicit"
    else:
        title, level, kind, confidence = text, 0, "", "pattern"
    title = title.strip()
    if _CLOSER.fullmatch(title):
        return {"level": 1, "kind": "closure", "title": title, "start_cp": start,
                "end_cp": end, "confidence": confidence, "role": "closure"}
    if len(title) <= 48 and _VOLUME.fullmatch(title):
        level, kind = 2, "volume"
    elif _ARTICLE.fullmatch(title):
        level, kind = 3, "article"
    elif _APPARATUS.fullmatch(title):
        level, kind = 1, "apparatus"
    elif _PARATEXT.fullmatch(title) and (markdown or symbol or
                                            (index > 0 and not lines[index - 1][2].strip() and next_text)):
        level, kind = 1, "paratext"
    if level:
        role = "notes" if kind == "apparatus" else "paratext" if kind == "paratext" else None
        return {"level": level, "kind": kind, "title": title,
                "start_cp": start, "end_cp": end, "confidence": confidence, "role": role}
    # A headword directly followed by an explicit explanation label is a
    # general layout cue; neither spelling nor source title is special-cased.
    if (len(text) <= 32 and not re.search(r"[。！？；：:]", text)
            and next_text.startswith("注解：")):
        return {"level": 3, "kind": "headword", "title": text, "start_cp": start,
                "end_cp": end, "confidence": "pattern", "role": None}
    if (len(text) <= 24 and re.fullmatch(r"[^\s。！？；：:，,、<>【】（）\[\]()]{1,12}(?:【[^】]{1,20}】)?", text)
            and next_text.startswith(("【", "（", "[", "<small>"))):
        return {"level": 3, "kind": "headword", "title": text, "start_cp": start,
                "end_cp": end, "confidence": "candidate", "role": None}
    # A short isolated line followed by prose/verse may be a title. Mark it
    # as a candidate, because title pages and tables of contents vary.
    preceding_blank = index > 0 and not lines[index - 1][2].strip()
    if (preceding_blank and 2 <= len(text) <= 32
            and not re.search(r"[。！？；：:，,、【】<>]", text)
            and next_text and bool(re.search(r"[。！？；，,]", next_text))):
        return {"level": 3, "kind": "plain_title", "title": text, "start_cp": start,
                "end_cp": end, "confidence": "candidate", "role": None}
    return None


def _title_like(text: str) -> bool:
    return 1 <= len(text) <= 45 and not re.search(r"[。！？；：，,<>【】]", text)


def _toc_ranges(lines: list[tuple[int, int, str]], raw_end: int) -> list[tuple[int, int]]:
    """Require a label or later repeated body titles, never shortness alone."""
    body_title_positions: dict[str, list[int]] = {}
    followed_by_prose = [False] * len(lines)
    following = ""
    for position in range(len(lines) - 1, -1, -1):
        text = lines[position][2].strip()
        if text and _title_like(text) and following and (len(following) > 45 or
                re.search(r"[。！？；，,]", following)):
            body_title_positions.setdefault(text, []).append(position)
            followed_by_prose[position] = True
        if text:
            following = text
    ranges = []
    index = 0
    while index < len(lines):
        if not _title_like(lines[index][2].strip()):
            index += 1
            continue
        stop = index
        titles = []
        while stop < len(lines):
            text = lines[stop][2].strip()
            if not text:
                next_line = stop + 1
                while next_line < len(lines) and not lines[next_line][2].strip():
                    next_line += 1
                if next_line - stop > 2 or next_line == len(lines):
                    break
                if len(titles) >= 3 and followed_by_prose[next_line]:
                    stop = next_line
                    break
                if _title_like(lines[next_line][2].strip()):
                    stop = next_line
                    continue
                break
            if not _title_like(text) or (len(titles) >= 3 and followed_by_prose[stop]):
                break
            titles.append(text)
            stop += 1
        labeled = any(_TOC_LABEL.fullmatch(title) for title in titles[:2])
        repeated = sum(1 for title in set(titles)
                       if body_title_positions.get(title, [0])[0] >= stop)
        if (labeled and len(titles) >= 4) or (len(titles) >= 8 and repeated >= 3):
            end = lines[stop][0] if stop < len(lines) else raw_end
            ranges.append((lines[index][0], end))
        index = max(index + 1, stop)
    return ranges


def _inside_note(note_spans: list[tuple[int, int]], position: int) -> bool:
    """Whether a cut lies in a paired note-like span; no author is inferred."""
    index = bisect.bisect_left(note_spans, (position, -1)) - 1
    return index >= 0 and note_spans[index][0] < position < note_spans[index][1]


def _association_links(raw: str, start: int, end: int) -> dict[int, tuple[str, int, int]]:
    """Record adjacent citation/explanation spans without inferring authorship."""
    links: dict[int, tuple[str, int, int]] = {}
    for match in _SENTENCE.finditer(raw, start, end):
        position = match.end()
        if position >= end:
            continue
        left_start = max(start, position - 240)
        left = raw[left_start:position].rstrip()
        right_raw = raw[position:min(end, position + 80)]
        right = right_raw.lstrip()
        right_start = position + len(right_raw) - len(right)
        next_line = _LINE_BREAK.search(raw, right_start, end)
        right_end = next_line.end() if next_line else end
        if left and right.startswith(("<small>", "【", "（", "[")):
            previous = list(_SENTENCE.finditer(raw[left_start:position]))
            citation_start = (left_start + previous[-2].end()
                              if len(previous) >= 2 else left_start)
            links[position] = ("attached_note", citation_start, right_end)
        elif _EXPLANATION.match(right) and (citations := list(_CITATION.finditer(left))):
            links[position] = ("quote_explanation", left_start + citations[-1].start(), right_end)
    return links


def _cuts(raw: str, start: int, end: int, target: int, maximum: int,
          note_spans: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], dict[int, tuple[str, int, int]]]:
    """Use natural boundaries, then a fixed fallback only for boundaryless runs."""
    links = _association_links(raw, start, end)
    if end - start <= maximum:
        return [(start, end)], links
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
    protected = {(left, right, basis) for basis, left, right in links.values()}
    protected_edges = set()
    for left, right, _ in protected:
        if right - left <= maximum:
            for position in (left, right):
                if start < position < end and not _inside_note(note_spans, position):
                    choices.append((position, 3))
                    protected_edges.add(position)
    choices = sorted(set(choices))
    positions = [position for position, _ in choices]
    result: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > maximum:
        minimum = cursor + min(target // 2, maximum // 2)
        maximum_here = cursor + maximum
        candidates = [item for item in choices[bisect.bisect_right(positions, cursor):
                                              bisect.bisect_right(positions, maximum_here)]
                      if item[0] >= minimum or item[0] in protected_edges]
        if candidates:
            position, _ = min(candidates, key=lambda item: (
                any(left < item[0] < right and right - left <= maximum
                    for left, right, _ in protected),
                item[0] in links, abs(item[0] - (cursor + target)) + item[1] * 80))
        else:
            # Keep this one fallback local to a long, unstructured stretch.
            position = cursor + min(target, maximum)
        result.append((cursor, position))
        cursor = position
    if cursor < end:
        result.append((cursor, end))
    return result, links


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
    toc_ranges = _toc_ranges(lines, len(raw))
    headings = [(index, found) for index in range(len(lines))
                if not any(left <= lines[index][0] < right for left, right in toc_ranges)
                if not _inside_note(note_spans_all, lines[index][0])
                and (found := _heading(lines, index, next_nonempty[index])) is not None]
    transitions: list[tuple[int, int, dict[str, Any] | None]] = []
    for left, right in toc_ranges:
        transitions.append((left, 1, {"level": 1, "kind": "toc", "title": "目录区",
                                      "start_cp": left, "end_cp": left, "confidence": "pattern",
                                      "role": "toc"}))
        transitions.append((right, 0, None))
    for index, heading in headings:
        transitions.append((heading["start_cp"], 1, heading))
        if heading["role"] == "closure":
            following_start = lines[index + 1][0] if index + 1 < len(lines) else len(raw)
            transitions.append((following_start, 0, None))
    transitions.sort(key=lambda event: (event[0], event[1]))
    events: list[tuple[int, dict[str, Any] | None, list[dict[str, Any]]]] = []
    stack: list[dict[str, Any]] = []
    for position, _, heading in transitions:
        if heading is None:
            stack.clear()
            events.append((position, None, []))
            continue
        if heading["role"] in {"toc", "closure", "notes", "paratext"} or heading["kind"] == "plain_title":
            stack.clear()
        else:
            if stack and stack[-1].get("role") in {"paratext", "notes"} and heading["kind"] in {"volume", "article"}:
                stack.clear()
            while stack and stack[-1]["level"] >= heading["level"]:
                stack.pop()
        if heading["role"] not in {"toc", "closure"}:
            stack.append(heading)
        events.append((position, heading, list(stack)))
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
            pieces, links = _cuts(raw, parent_start, parent_end, target, maximum, note_spans)
            parent_id = "par_" + hashlib.sha256(f"{source_id}:{parent_start}:{parent_end}".encode()).hexdigest()
            heading_path = [{key: item[key] for key in ("kind", "title", "start_cp", "end_cp", "confidence")}
                            for item in path]
            toc_candidate = bool(heading and (heading["role"] == "toc" or
                                              not raw[heading["end_cp"]:parent_end].strip()))
            for part_index, (start, end) in enumerate(pieces, 1):
                output.append({
                    "start_cp": start, "end_cp": end,
                    "role": (heading["role"] if heading and heading["role"] else
                             "entry" if heading and heading["level"] >= 3 else
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
                        "association_links": [{"at_cp": position, "basis": basis,
                                               "range_start_cp": left, "range_end_cp": right,
                                               "within_limit": right - left <= maximum}
                                              for position, (basis, left, right) in links.items()
                                              if start < position < end],
                        "association_continued_from_previous": next(
                            (basis for basis, left, right in links.values() if left < start < right), None),
                        "association_continues_next": next(
                            (basis for basis, left, right in links.values() if left < end < right), None)
                            if part_index < len(pieces) else None,
                    },
                })
    return output

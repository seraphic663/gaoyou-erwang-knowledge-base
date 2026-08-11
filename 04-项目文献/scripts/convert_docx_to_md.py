from __future__ import annotations

import argparse
import os
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


TITLE_NOTE_A = (
    "\u672c\u6587\u4ef6\u7531 `{source}` \u62bd\u53d6\u7eaf\u6587\u672c\u751f\u6210\uff1b"
    "\u4fdd\u7559\u53ef\u590d\u5236\u6587\u5b57\uff0c\u672a\u505a\u6821\u52d8\u3002"
    "\u5c0f\u5b57\u4ee5 `<small>` \u6807\u8bb0\uff1b"
    "\u76ee\u5f55\u3001\u5185\u90e8\u8df3\u8f6c\u3001\u4e66\u7b7e\u548c\u56fe\u7247\u7248\u5f0f\u4ee5\u539f DOCX \u4e3a\u51c6\u3002"
)
TITLE_NOTE_B = (
    "\u672c\u6587\u4ef6\u7531 `{source}` \u62bd\u53d6\u7eaf\u6587\u672c\u751f\u6210\uff1b"
    "\u4fdd\u7559 OCR \u539f\u6587\uff0c\u672a\u505a\u6821\u52d8\u3002"
)


@dataclass
class StyleInfo:
    paragraph_sizes: dict[str, int] = field(default_factory=dict)
    character_sizes: dict[str, int] = field(default_factory=dict)
    paragraph_outline: dict[str, int] = field(default_factory=dict)


@dataclass
class Paragraph:
    index: int
    style: str
    text: str
    markdown_text: str
    has_hyperlink: bool
    has_drawing: bool
    has_toc_field: bool
    sizes: list[int]


@dataclass
class Comment:
    comment_id: str
    author: str
    date: str
    anchor: str
    text: str


@dataclass
class CurrentTask:
    source: Path
    output: Path
    title: str
    paragraph_limit: int | None = None
    scope_note: str = ""


def qname(name: str) -> str:
    return W + name


def attr_val(elem: ET.Element, name: str) -> str | None:
    return elem.attrib.get(qname(name))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_xml(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError:
        return None


def load_styles(zf: zipfile.ZipFile) -> StyleInfo:
    styles = read_xml(zf, "word/styles.xml")
    info = StyleInfo()
    if styles is None:
        return info
    for style in styles.iter(qname("style")):
        style_id = attr_val(style, "styleId")
        style_type = attr_val(style, "type")
        if not style_id:
            continue
        rpr = style.find(qname("rPr"))
        size = None
        if rpr is not None:
            sz = rpr.find(qname("sz"))
            if sz is not None:
                raw = attr_val(sz, "val")
                if raw and raw.isdigit():
                    size = int(raw)
        if size is not None:
            if style_type == "paragraph":
                info.paragraph_sizes[style_id] = size
            elif style_type == "character":
                info.character_sizes[style_id] = size
        ppr = style.find(qname("pPr"))
        if ppr is not None:
            outline = ppr.find(qname("outlineLvl"))
            if outline is not None:
                raw = attr_val(outline, "val")
                if raw and raw.isdigit():
                    info.paragraph_outline[style_id] = int(raw)
    return info


def run_size(run: ET.Element, styles: StyleInfo, paragraph_style: str) -> int | None:
    rpr = run.find(qname("rPr"))
    if rpr is not None:
        sz = rpr.find(qname("sz"))
        if sz is not None:
            raw = attr_val(sz, "val")
            if raw and raw.isdigit():
                return int(raw)
        rstyle = rpr.find(qname("rStyle"))
        if rstyle is not None:
            style_id = attr_val(rstyle, "val")
            if style_id in styles.character_sizes:
                return styles.character_sizes[style_id]
    return styles.paragraph_sizes.get(paragraph_style)


def is_small_size(size: int | None) -> bool:
    return size is not None and size <= 18


def wrap_small(text: str) -> str:
    text = clean_text(text)
    if not text:
        return ""
    return f"<small>{text}</small>"


def paragraph_style(paragraph: ET.Element) -> str:
    ppr = paragraph.find(qname("pPr"))
    if ppr is None:
        return ""
    pstyle = ppr.find(qname("pStyle"))
    if pstyle is None:
        return ""
    return attr_val(pstyle, "val") or ""


def paragraph_to_text(paragraph: ET.Element, styles: StyleInfo) -> tuple[str, str, list[int]]:
    p_style = paragraph_style(paragraph)
    plain_parts: list[str] = []
    md_parts: list[tuple[bool, str]] = []
    sizes: list[int] = []

    for run in paragraph.iter(qname("r")):
        pieces: list[str] = []
        for child in run:
            if child.tag == qname("t"):
                pieces.append(child.text or "")
            elif child.tag == qname("tab"):
                pieces.append(" ")
            elif child.tag in {qname("br"), qname("cr")}:
                pieces.append(" ")
            elif child.tag == qname("footnoteReference"):
                fid = attr_val(child, "id")
                if fid and not fid.startswith("-"):
                    pieces.append(f"[^{fid}]")
            elif child.tag == qname("endnoteReference"):
                eid = attr_val(child, "id")
                if eid and not eid.startswith("-"):
                    pieces.append(f"[^endnote-{eid}]")
        text = "".join(pieces)
        if not text:
            continue
        size = run_size(run, styles, p_style)
        if size is not None:
            sizes.append(size)
        small = is_small_size(size)
        plain_parts.append(text)
        md_parts.append((small, text))

    plain = clean_text("".join(plain_parts))
    if not plain:
        return "", "", sizes

    # Merge adjacent runs that share the same small/normal state before wrapping.
    merged: list[tuple[bool, str]] = []
    for small, text in md_parts:
        if merged and merged[-1][0] == small:
            merged[-1] = (small, merged[-1][1] + text)
        else:
            merged.append((small, text))

    rendered: list[str] = []
    for small, text in merged:
        part = clean_text(text)
        if not part:
            continue
        rendered.append(wrap_small(part) if small else part)
    markdown = clean_text(" ".join(rendered))
    return plain, markdown, sizes


def extract_notes(zf: zipfile.ZipFile, path: str, prefix: str = "") -> dict[str, str]:
    root = read_xml(zf, path)
    if root is None:
        return {}
    notes: dict[str, str] = {}
    tag = qname("footnote") if "footnote" in path else qname("endnote")
    for note in root.iter(tag):
        note_id = attr_val(note, "id")
        if not note_id or note_id.startswith("-"):
            continue
        text = clean_text("".join(t.text or "" for t in note.iter(qname("t"))))
        if text:
            notes[prefix + note_id] = text
    return notes


def exact_element_text(element: ET.Element) -> str:
    parts: list[str] = []
    for child in element.iter():
        if child.tag == qname("t"):
            parts.append(child.text or "")
        elif child.tag == qname("tab"):
            parts.append("\t")
        elif child.tag in {qname("br"), qname("cr")}:
            parts.append("<br>")
        elif child.tag == qname("footnoteReference"):
            note_id = attr_val(child, "id")
            if note_id and not note_id.startswith("-"):
                parts.append(f"[^{note_id}]")
        elif child.tag == qname("endnoteReference"):
            note_id = attr_val(child, "id")
            if note_id and not note_id.startswith("-"):
                parts.append(f"[^endnote-{note_id}]")
    return "".join(parts)


def extract_comment_anchors(document: ET.Element) -> dict[str, str]:
    active: list[str] = []
    anchor_parts: dict[str, list[str]] = {}
    for element in document.iter():
        if element.tag == qname("commentRangeStart"):
            comment_id = attr_val(element, "id")
            if comment_id:
                active.append(comment_id)
                anchor_parts.setdefault(comment_id, [])
        elif element.tag == qname("commentRangeEnd"):
            comment_id = attr_val(element, "id")
            if comment_id in active:
                active.remove(comment_id)
        elif element.tag == qname("t"):
            for comment_id in active:
                anchor_parts.setdefault(comment_id, []).append(element.text or "")
        elif element.tag == qname("tab"):
            for comment_id in active:
                anchor_parts.setdefault(comment_id, []).append("\t")
        elif element.tag in {qname("br"), qname("cr")}:
            for comment_id in active:
                anchor_parts.setdefault(comment_id, []).append("<br>")
    return {comment_id: "".join(parts) for comment_id, parts in anchor_parts.items()}


def extract_comments(zf: zipfile.ZipFile, document: ET.Element) -> list[Comment]:
    comments_root = read_xml(zf, "word/comments.xml")
    if comments_root is None:
        return []
    anchors = extract_comment_anchors(document)
    comments: list[Comment] = []
    for element in comments_root.iter(qname("comment")):
        comment_id = attr_val(element, "id") or ""
        paragraph_texts = [
            exact_element_text(paragraph)
            for paragraph in element.iter(qname("p"))
        ]
        comments.append(
            Comment(
                comment_id=comment_id,
                author=attr_val(element, "author") or "",
                date=attr_val(element, "date") or "",
                anchor=anchors.get(comment_id, ""),
                text="\n\n".join(text for text in paragraph_texts if text.strip()),
            )
        )
    return comments


def parse_current_docx(path: Path) -> tuple[list[str], dict[str, str], list[Comment], Counter]:
    stats: Counter = Counter()
    with zipfile.ZipFile(path) as zf:
        document = read_xml(zf, "word/document.xml")
        if document is None:
            raise ValueError(f"Missing word/document.xml in {path}")
        paragraphs: list[str] = []
        for paragraph in document.iter(qname("p")):
            text = exact_element_text(paragraph)
            if text.strip():
                paragraphs.append(text)
        notes = extract_notes(zf, "word/footnotes.xml")
        notes.update(extract_notes(zf, "word/endnotes.xml", "endnote-"))
        comments = extract_comments(zf, document)
        stats["paragraphs"] = len(paragraphs)
        stats["notes"] = len(notes)
        stats["comments"] = len(comments)
        stats["tables"] = len(list(document.iter(qname("tbl"))))
        stats["drawings"] = len(list(document.iter(qname("drawing"))))
    return paragraphs, notes, comments, stats


def parse_docx(path: Path) -> tuple[list[Paragraph], dict[str, str], Counter]:
    stats: Counter = Counter()
    with zipfile.ZipFile(path) as zf:
        styles = load_styles(zf)
        root = read_xml(zf, "word/document.xml")
        if root is None:
            raise ValueError(f"Missing word/document.xml in {path}")
        notes = extract_notes(zf, "word/footnotes.xml")
        notes.update(extract_notes(zf, "word/endnotes.xml", "endnote-"))
        paragraphs: list[Paragraph] = []
        for index, paragraph in enumerate(root.iter(qname("p")), 1):
            plain, markdown, sizes = paragraph_to_text(paragraph, styles)
            has_drawing = bool(list(paragraph.iter(WP + "inline")) or list(paragraph.iter(WP + "anchor")))
            has_hyperlink = bool(list(paragraph.iter(qname("hyperlink"))))
            has_toc_field = any(
                (elem.text or "").strip().startswith("TOC")
                for elem in paragraph.iter(qname("instrText"))
            )
            if has_drawing:
                stats["drawing_paragraphs"] += 1
                if not plain:
                    stats["drawing_only_paragraphs"] += 1
            if has_hyperlink:
                stats["hyperlink_paragraphs"] += 1
            if has_toc_field:
                stats["toc_fields"] += 1
            if not plain:
                continue
            p_style = paragraph_style(paragraph)
            paragraphs.append(
                Paragraph(
                    index=index,
                    style=p_style,
                    text=plain,
                    markdown_text=markdown,
                    has_hyperlink=has_hyperlink,
                    has_drawing=has_drawing,
                    has_toc_field=has_toc_field,
                    sizes=sizes,
                )
            )
    stats["paragraphs"] = len(paragraphs)
    stats["notes"] = len(notes)
    return paragraphs, notes, stats


def drop_initial_toc(paragraphs: list[Paragraph]) -> list[Paragraph]:
    if not any(p.has_toc_field or p.text.lower() == "table of contents" for p in paragraphs[:20]):
        return paragraphs

    # The generated TOC is a long run of hyperlink-only entries. Keep title-page
    # matter by resuming at the first stable run of non-link text after the TOC.
    for i in range(len(paragraphs)):
        window = paragraphs[i : i + 5]
        if len(window) == 5 and all(not p.has_hyperlink and not p.has_toc_field for p in window):
            return paragraphs[i:]
    return [p for p in paragraphs if not p.has_hyperlink and not p.has_toc_field]


def should_skip_paragraph(p: Paragraph) -> bool:
    if p.has_toc_field:
        return True
    text = p.text.strip()
    if text.lower() == "table of contents":
        return True
    if text in {"\u76ee\u5f55", "\u76ee\u9304", "\u603b\u76ee\u5f55", "\u7e3d\u76ee\u9304", "\u8fd4\u56de\u603b\u76ee\u5f55"}:
        return True
    return False


def is_page_marker(text: str) -> re.Match[str] | None:
    return re.fullmatch(r"\u3010\u7b2c(\d+)\u9875\u3011", text)


def heading_level_a(p: Paragraph) -> int | None:
    style = p.style
    text = p.text.strip()
    size = max(p.sizes) if p.sizes else None
    length = len(text)
    no_sentence_end = not re.search(r"[。！？；;]$", text)

    if style == "Heading 1":
        return 2
    if style == "Heading 2":
        return 2
    if style == "Heading 3":
        return 3
    if style in {"Para 11", "Para 18", "Para 19"}:
        return 2
    if style in {"Para 03", "Para 08"}:
        return 3
    if style:
        return None
    if size is not None:
        if size >= 36 and length <= 80:
            return 2
        if size >= 28 and length <= 120 and no_sentence_end:
            return 3
        if size >= 24 and length <= 160 and no_sentence_end and not text.startswith(("\u300a", "\u2018", "\u201c", "\u300c")):
            return 3
    if not p.sizes and length <= 18 and no_sentence_end:
        if re.search(r"[\u5377\u5e8f\u9304\u5f55]|\u5f01\u8a00|\u81ea\u5e8f", text) or length <= 6:
            return 3
    return None


def render_markdown(title: str, source: str, paragraphs: list[Paragraph], notes: dict[str, str], kind: str) -> str:
    note = TITLE_NOTE_A if kind == "A" else TITLE_NOTE_B
    lines: list[str] = [f"# {title}", "", f"> {note.format(source=source)}", ""]

    for p in paragraphs:
        if should_skip_paragraph(p):
            continue
        page = is_page_marker(p.text)
        if page is not None:
            lines.extend([f"### \u7b2c{page.group(1)}\u9875", ""])
            continue

        if kind == "A":
            level = heading_level_a(p)
            if level is not None:
                lines.extend([f"{'#' * level} {p.markdown_text}", ""])
                continue

        if p.markdown_text.startswith("<small>") and p.markdown_text.endswith("</small>"):
            lines.extend([p.markdown_text, ""])
        else:
            lines.extend([p.markdown_text, ""])

    if notes:
        lines.extend(["## \u811a\u6ce8", ""])
        for note_id in sorted(notes, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)):
            lines.extend([f"[^{note_id}]: {notes[note_id]}", ""])

    return "\n".join(lines).rstrip() + "\n"


def output_name_for_b(path: Path) -> str:
    mapping = {
        "\u7b2c\u4e00\u518c": "(1)",
        "\u7b2c\u4e8c\u518c": "(2)",
        "\u7b2c\u4e09\u518c": "(3)",
        "\u7b2c\u56db\u518c": "(4)",
        "\u7b2c\u4e94\u518c": "(5)",
        "\u7b2c\u516d\u518c": "(6)",
    }
    for key, suffix in mapping.items():
        if key in path.stem:
            return f"\u9ad8\u90ae\u4e8c\u738b\u5408\u96c6{suffix}.md"
    return path.with_suffix(".md").name


def convert_file(path: Path, kind: str) -> tuple[Path, Counter]:
    paragraphs, notes, stats = parse_docx(path)
    if kind == "A":
        paragraphs = drop_initial_toc(paragraphs)
        out_path = path.with_suffix(".md")
        title = path.stem
    elif kind == "B":
        out_path = path.with_name(output_name_for_b(path))
        title = out_path.stem
    else:
        raise ValueError(kind)

    md = render_markdown(title, path.name, paragraphs, notes, kind)
    out_path.write_text(md, encoding="utf-8")
    stats["output_chars"] = len(md)
    stats["headings"] = len(re.findall(r"^#{2,6} ", md, flags=re.MULTILINE))
    stats["small_tags"] = md.count("<small>")
    return out_path, stats


CURRENT_BODY_START = "<!-- DOCX-BODY-START -->"
CURRENT_BODY_END = "<!-- DOCX-BODY-END -->"


def comment_sort_key(comment: Comment) -> tuple[bool, int | str]:
    if comment.comment_id.isdigit():
        return False, int(comment.comment_id)
    return True, comment.comment_id


def render_current_markdown(
    task: CurrentTask,
    paragraphs: list[str],
    notes: dict[str, str],
    comments: list[Comment],
) -> str:
    relative_source = Path(os.path.relpath(task.source, task.output.parent)).as_posix()
    lines = [
        f"# {task.title}",
        "",
        f"> 归档底本：[{task.source.name}](<{relative_source}>)",
        "> 本文逐段保留 DOCX 中可复制的正文文字，未做校勘、繁简转换或标点统一；字体、分页、批注位置等版式以归档 DOCX 为准。",
    ]
    if task.scope_note:
        lines.append(f"> 内容范围：{task.scope_note}")
    lines.extend(["", CURRENT_BODY_START, "", "\n\n".join(paragraphs), "", CURRENT_BODY_END, ""])

    if notes:
        lines.extend(["## 脚注", ""])
        for note_id in sorted(notes, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)):
            lines.extend([f"[^{note_id}]: {notes[note_id]}", ""])

    if comments:
        lines.extend(["## Word 批注", ""])
        for comment in sorted(comments, key=comment_sort_key):
            lines.extend([f"### 批注 {comment.comment_id}", ""])
            if comment.author:
                lines.append(f"- 作者：{comment.author}")
            if comment.date:
                lines.append(f"- 时间：{comment.date}")
            if comment.anchor:
                lines.append(f"- 锚定文字：{comment.anchor.replace(chr(10), '<br>')}")
            lines.extend(["", comment.text, ""])
    return "\n".join(lines).rstrip() + "\n"


def current_tasks(root: Path) -> list[CurrentTask]:
    archive_current = root.parent / "05-归档文献" / "04-项目文献" / "0-当前阅读"
    output_current = root / "0-当前阅读"
    template_names = [
        "《广雅疏证》“始也”条.docx",
        "《广雅疏证》“敬也”.docx",
        "《经义述闻》终风且暴.docx",
        "《经传释词》“允”标注.docx",
        "《读书杂志》平原之隰.docx",
    ]
    tasks = [
        CurrentTask(
            source=archive_current / "整理标注模版" / name,
            output=output_current / "整理标注模版" / Path(name).with_suffix(".md").name,
            title=Path(name).stem,
        )
        for name in template_names
    ]
    tasks.append(
        CurrentTask(
            source=archive_current / "“有杞有堂”“终风且暴”.docx",
            output=output_current / "《经义述闻》有紀有堂.md",
            title="《经义述闻》有紀有堂",
            paragraph_limit=5,
            scope_note="仅保留原合并文档中独有的“有紀有堂”条；其“終風且暴”条已由整理标注模板的独立 Markdown 完整保存。",
        )
    )
    return tasks


def convert_current_task(task: CurrentTask) -> tuple[Path, Counter]:
    paragraphs, notes, comments, stats = parse_current_docx(task.source)
    if task.paragraph_limit is not None:
        paragraphs = paragraphs[: task.paragraph_limit]
        stats["selected_paragraphs"] = len(paragraphs)
        if comments or notes:
            raise ValueError(f"Partial current-reading conversion would drop notes or comments: {task.source}")
    markdown = render_current_markdown(task, paragraphs, notes, comments)
    expected_body = "\n\n".join(paragraphs)
    rendered_body = markdown.split(CURRENT_BODY_START, 1)[1].split(CURRENT_BODY_END, 1)[0].strip("\n")
    if rendered_body != expected_body:
        raise ValueError(f"Generated Markdown body differs from DOCX extraction: {task.source}")
    for comment in comments:
        if comment.text and comment.text not in markdown:
            raise ValueError(f"Missing comment {comment.comment_id} in generated Markdown: {task.source}")
        if comment.anchor and comment.anchor.replace("\n", "<br>") not in markdown:
            raise ValueError(f"Missing comment anchor {comment.comment_id} in generated Markdown: {task.source}")
    task.output.parent.mkdir(parents=True, exist_ok=True)
    task.output.write_text(markdown, encoding="utf-8")
    stats["output_chars"] = len(markdown)
    return task.output, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert project DOCX sources to Markdown.")
    parser.add_argument("--root", default=".", help="Project literature root. Defaults to current directory.")
    parser.add_argument("--section", choices=["A", "B", "current", "all"], default="all")
    args = parser.parse_args()

    root = Path(args.root)
    tasks: list[tuple[str, Path]] = []
    if args.section in {"A", "all"}:
        a_dir = root / "A-\u539f\u8457\u539f\u5178"
        tasks.extend(("A", p) for p in sorted(a_dir.glob("*.docx")) if not p.name.startswith("~$"))
    if args.section in {"B", "all"}:
        b_dir = root / "B-\u4e00\u7ea7\u8d44\u6599"
        tasks.extend(("B", p) for p in sorted(b_dir.glob("*.docx")) if not p.name.startswith("~$"))

    current = current_tasks(root) if args.section in {"current", "all"} else []
    if not tasks and not current:
        raise SystemExit("No DOCX files found.")

    for kind, path in tasks:
        out_path, stats = convert_file(path, kind)
        print(
            f"{path} -> {out_path} | "
            f"paragraphs={stats['paragraphs']} headings={stats['headings']} "
            f"small={stats['small_tags']} notes={stats['notes']} "
            f"hyperlink_paragraphs={stats['hyperlink_paragraphs']} "
            f"drawing_paragraphs={stats['drawing_paragraphs']} "
            f"drawing_only={stats['drawing_only_paragraphs']}"
        )
    for task in current:
        if not task.source.exists():
            raise FileNotFoundError(task.source)
        out_path, stats = convert_current_task(task)
        print(
            f"{task.source} -> {out_path} | "
            f"paragraphs={stats['paragraphs']} selected={stats.get('selected_paragraphs', stats['paragraphs'])} "
            f"comments={stats['comments']} notes={stats['notes']} "
            f"tables={stats['tables']} drawings={stats['drawings']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

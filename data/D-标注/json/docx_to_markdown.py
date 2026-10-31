"""Transcribe one DOCX into the existing document/case Markdown layout."""
from __future__ import annotations

import argparse
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "data" / "D-标注"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def convert(source: Path, filename: str, title: str, *, overwrite: bool = False) -> tuple[Path, Path]:
    document = BASE / "02-文档Markdown" / filename
    case = BASE / "03-案例Markdown" / filename
    if not overwrite and (document.exists() or case.exists()):
        raise FileExistsError(filename)
    source = source.resolve()
    with zipfile.ZipFile(source) as package:
        relationships = {}
        if "word/_rels/document.xml.rels" in package.namelist():
            relationships = {
                node.attrib["Id"]: node.attrib.get("Target", "")
                for node in ET.fromstring(package.read("word/_rels/document.xml.rels"))
            }
        assets = {}

        def inline(node: ET.Element) -> str:
            if node.tag == W + "t":
                return node.text or ""
            if node.tag == W + "tab":
                return "\t"
            if node.tag in {W + "br", W + "cr"}:
                return "<br>"
            if node.tag in {W + "footnoteReference", W + "endnoteReference"}:
                kind = "fn" if node.tag == W + "footnoteReference" else "en"
                return f"[^{kind}-{node.attrib.get(W + 'id', '')}]"
            if node.tag == A + "blip":
                target = relationships.get(node.attrib.get(R + "embed", ""))
                if not target:
                    return ""
                member = posixpath.normpath(posixpath.join("word", target))
                if member not in assets:
                    asset = BASE / "02-文档Markdown" / "assets" / "20261027" / f"{filename[:3]}-{Path(target).name}"
                    asset.parent.mkdir(parents=True, exist_ok=True)
                    asset.write_bytes(package.read(member))
                    assets[member] = asset
                relative = "../02-文档Markdown/" + assets[member].relative_to(BASE / "02-文档Markdown").as_posix()
                return f"![DOCX内嵌字形](<{quote(relative, safe='/') }>)"
            return "".join(inline(child) for child in node)

        body = ET.fromstring(package.read("word/document.xml")).find(W + "body")
        blocks = []
        for node in body:
            if node.tag == W + "p":
                blocks.append(inline(node))
            elif node.tag == W + "tbl":
                for row in node.findall(W + "tr"):
                    cells = ["<br>".join(inline(p) for p in cell.findall(W + "p")) for cell in row.findall(W + "tc")]
                    blocks.append(" | ".join(cells))
        content = "\n\n".join(blocks).strip()
        appendix = []
        if "word/comments.xml" in package.namelist():
            comments = ET.fromstring(package.read("word/comments.xml"))
            for node in comments:
                text = "\n\n".join(inline(p) for p in node.findall(W + "p"))
                appendix.append(f"### 批注 {node.attrib.get(W + 'id', '')}\n\n作者：{node.attrib.get(W + 'author', '未知')}；时间：{node.attrib.get(W + 'date', '')}\n\n{text}")
        for kind in ["footnotes", "endnotes"]:
            member = f"word/{kind}.xml"
            if member in package.namelist():
                for note in ET.fromstring(package.read(member)):
                    if note.attrib.get(W + "type") in {"separator", "continuationSeparator", "continuationNotice"}:
                        continue
                    text = "\n\n".join(inline(p) for p in note.findall(W + "p"))
                    if text.strip():
                        label = "fn" if kind == "footnotes" else "en"
                        appendix.append(f"[^{label}-{note.attrib.get(W + 'id', '')}]: {text}")
    relative_source = "../01-原始DOCX/" + source.relative_to(BASE / "01-原始DOCX").as_posix()
    header = f"# {title}\n\n> 原始 DOCX：[{source.name}](<{quote(relative_source, safe='/')}>)\n> 本文由脚本按 DOCX OOXML 段落顺序转写，未做校勘、繁简转换或标点统一；内嵌字形以原图保留，原始版式以 DOCX 为准。\n\n"
    text = header + "<!-- DOCX-BODY-START -->\n\n" + content + "\n\n<!-- DOCX-BODY-END -->\n"
    if appendix:
        text += "\n## Word 批注与注释\n\n" + "\n\n".join(appendix) + "\n"
    document.write_text(text, encoding="utf-8")
    case.write_text(text, encoding="utf-8")
    return document, case


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("filename")
    parser.add_argument("--title", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    for result in convert(args.source, args.filename, args.title, overwrite=args.overwrite):
        print(result.relative_to(ROOT).as_posix())

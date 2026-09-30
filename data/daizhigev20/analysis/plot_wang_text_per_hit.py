from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / "wang_hit_matrix.tsv"
IMAGE_PATH = HERE / "wang_text_per_exact_hit.png"
TABLE_PATH = HERE / "wang_text_per_exact_hit.tsv"
SUMMARY_PATH = HERE / "wang_text_per_exact_hit.json"

BLUE = (44, 104, 173)
ORANGE = (219, 111, 39)
RED = (180, 65, 65)
DARK = (40, 40, 40)
MUTED = (95, 95, 95)
GRID = (225, 225, 225)


def find_font(size: int):
    for font_path in (
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ):
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def centered_text(draw, center_x, y, text, font, fill):
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((center_x - (box[2] - box[0]) / 2, y), text, font=font, fill=fill)


def body_text(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2]
    return text


def body_char_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    return len(re.sub(r"s+", "", body_text(text)))


def format_count(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:.0f}"


def main():
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="	"))
    if not rows:
        raise SystemExit(f"No rows found in {SOURCE}")

    total_titles = len(rows)
    exact_ranked = sorted(rows, key=lambda row: (-int(row["exact_hits"]), row["title_key"]))
    high_end = math.ceil(total_titles * 0.10)
    middle_end = math.ceil(total_titles * 0.25)

    for rank, row in enumerate(exact_ranked, start=1):
        row["rank"] = rank
        row["exact_hits"] = int(row["exact_hits"])
        row["file_count"] = int(row["file_count"])
        paths = [ROOT / item.strip() for item in row["files"].split("|")]
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Missing corpus files for {row['title']}: {missing}")
        row["body_chars"] = sum(body_char_count(path) for path in paths)
        row["chars_per_exact_hit"] = (
            row["body_chars"] / row["exact_hits"] if row["exact_hits"] else None
        )
        row["tier"] = (
            "高频" if rank <= high_end
            else "中频" if rank <= middle_end
            else "低频"
        )

    fields = [
        "rank", "tier", "title", "title_key", "file_count", "files",
        "body_chars", "exact_hits", "chars_per_exact_hit",
    ]
    with TABLE_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="	")
        writer.writeheader()
        for row in exact_ranked:
            writer.writerow({field: row.get(field, "") for field in fields})

    tier_ranges = {
        "高频": exact_ranked[:high_end],
        "中频": exact_ranked[high_end:middle_end],
        "低频": exact_ranked[middle_end:],
    }
    tier_summary = {}
    for tier, group in tier_ranges.items():
        total_chars = sum(row["body_chars"] for row in group)
        total_hits = sum(row["exact_hits"] for row in group)
        valid = [
            row["chars_per_exact_hit"]
            for row in group
            if row["chars_per_exact_hit"] is not None
        ]
        tier_summary[tier] = {
            "title_count": len(group),
            "exact_zero_titles": len(group) - len(valid),
            "body_chars": total_chars,
            "exact_hits": total_hits,
            "weighted_chars_per_exact_hit": total_chars / total_hits if total_hits else None,
            "mean_title_chars_per_exact_hit": sum(valid) / len(valid) if valid else None,
            "median_title_chars_per_exact_hit": sorted(valid)[len(valid) // 2] if valid else None,
        }

    summary = {
        "metric": "正文字符数（去除 YAML 头信息和空白）/ exact 命中次数",
        "ordering": "exact 命中降序；高频10%、中频10%-25%、低频25%-100%",
        "same_title_counted_once": True,
        "total_markdown_files": sum(int(row["file_count"]) for row in exact_ranked),
        "unique_titles": total_titles,
        "exact_positive_titles": sum(row["exact_hits"] > 0 for row in exact_ranked),
        "exact_zero_titles": sum(row["exact_hits"] == 0 for row in exact_ranked),
        "tiers": tier_summary,
        "table": str(TABLE_PATH),
        "chart": str(IMAGE_PATH),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    width, height = 1600, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = find_font(34)
    body_font = find_font(18)
    axis_font = find_font(16)
    small_font = find_font(15)
    table_font = find_font(16)

    draw.text((75, 25), "王氏四种：每次 exact 命中的平均正文字符数", fill=DARK, font=title_font)
    draw.text(
        (75, 76),
        "每个规范书名：正文字符数 ÷ exact 命中次数；同标题只计一次，按高频→中频→低频排列",
        fill=MUTED,
        font=body_font,
    )

    left, top, right, bottom = 145, 155, 1430, 590
    x_at = lambda pct: left + (right - left) * pct / 100
    max_ratio = max(
        row["chars_per_exact_hit"] or 1
        for row in exact_ranked
    )
    y_max_power = max(1, math.ceil(math.log10(max_ratio)))
    y_at = lambda value: bottom - math.log10(max(value, 1)) / y_max_power * (bottom - top)

    bands = [
        (0, high_end, "高频 26名", (240, 247, 252)),
        (high_end, middle_end, "中频 37名", (251, 247, 239)),
        (middle_end, total_titles, "低频 189名（22名无 exact）", (246, 247, 248)),
    ]
    for start, end, _, color in bands:
        draw.rectangle(
            (
                round(x_at(start / total_titles * 100)),
                top,
                round(x_at(end / total_titles * 100)),
                bottom,
            ),
            fill=color,
        )

    for power in range(0, y_max_power + 1):
        value = 10 ** power
        y = y_at(value)
        draw.line((left, y, right, y), fill=GRID, width=1)
        draw.text((left - 62, y - 9), format_count(value), fill=MUTED, font=axis_font)

    for pct in (0, 10, 25, 50, 75, 100):
        x = x_at(pct)
        draw.line((x, top, x, bottom), fill=GRID, width=1)
        centered_text(draw, x, bottom + 8, f"{pct}%", axis_font, MUTED)

    draw.line((left, top, left, bottom), fill=(70, 70, 70), width=2)
    draw.line((left, bottom, right, bottom), fill=(70, 70, 70), width=2)
    for boundary in (high_end, middle_end):
        x = round(x_at(boundary / total_titles * 100))
        draw.line((x, top, x, bottom), fill=(155, 155, 155), width=1)

    draw.text((75, 105), "正文字符数 / exact 命中次数（log）", fill=MUTED, font=axis_font)
    centered_text(draw, (left + right) / 2, bottom + 36, "规范书名排名占比（高频 → 中频 → 低频）", axis_font, MUTED)

    for start, end, label, _ in bands:
        center = (x_at(start / total_titles * 100) + x_at(end / total_titles * 100)) / 2
        centered_text(draw, center, 128, label, small_font, DARK)

    draw.line((1015, 105, 1050, 105), fill=BLUE, width=4)
    draw.text((1060, 94), "正文字符数 / exact 命中", fill=DARK, font=small_font)

    segment = []
    for row in exact_ranked:
        if row["chars_per_exact_hit"] is None:
            if len(segment) >= 2:
                draw.line(segment, fill=BLUE, width=3)
            segment = []
            continue
        segment.append((
            x_at(row["rank"] / total_titles * 100),
            y_at(row["chars_per_exact_hit"]),
        ))
    if len(segment) >= 2:
        draw.line(segment, fill=BLUE, width=3)

    table_left, table_right = 75, 1525
    table_top = 680
    draw.line((table_left, table_top - 5, table_right, table_top - 5), fill=(185, 185, 185), width=1)
    draw.line((table_left, table_top + 30, table_right, table_top + 30), fill=(210, 210, 210), width=1)
    headers = ["频段", "规范书名", "可计算", "exact=0", "总字符 / 总 exact hit", "书名比值中位数"]
    values = []
    for tier in ("高频", "中频", "低频"):
        item = tier_summary[tier]
        values.append([
            tier,
            str(item["title_count"]),
            str(item["title_count"] - item["exact_zero_titles"]),
            str(item["exact_zero_titles"]),
            f"{item['weighted_chars_per_exact_hit']:,.0f}",
            f"{item['median_title_chars_per_exact_hit']:,.0f}" if item["median_title_chars_per_exact_hit"] is not None else "—",
        ])
    col_widths = [150, 150, 150, 150, 290, 240]
    edges = [table_left]
    for size in col_widths:
        edges.append(edges[-1] + size)
    for idx, header in enumerate(headers):
        centered_text(draw, (edges[idx] + edges[idx + 1]) / 2, table_top, header, table_font, MUTED)
    for row_idx, row_values in enumerate(values):
        y = table_top + 56 + row_idx * 34
        for idx, value in enumerate(row_values):
            centered_text(draw, (edges[idx] + edges[idx + 1]) / 2, y, value, table_font, DARK)
    draw.line((table_left, table_top + 56 + len(values) * 34 - 8, table_right, table_top + 56 + len(values) * 34 - 8), fill=(210, 210, 210), width=1)
    draw.text(
        (75, 825),
        "正文字符数不含 YAML 头信息和空白；exact=0 的书名不定义“字数/命中”，图中不连线。",
        fill=MUTED,
        font=small_font,
    )
    image.save(IMAGE_PATH)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

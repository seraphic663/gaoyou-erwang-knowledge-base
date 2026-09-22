from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "wang_hit_matrix.tsv"
IMAGE_PATH = HERE / "wang_hit_top_k_coverage.png"
TABLE_PATH = HERE / "wang_hit_top_k_coverage.tsv"
POINTS_PATH = HERE / "wang_hit_coverage_curve_points.tsv"

BLUE = (44, 104, 173)
ORANGE = (219, 111, 39)
K_VALUES = (1, 5, 10, 25, 50, 75, 100)


def find_font(size: int):
    for font_path in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ):
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def centered_text(draw: ImageDraw.ImageDraw, center_x: float, y: int, text: str, font, fill):
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((center_x - (box[2] - box[0]) / 2, y), text, font=font, fill=fill)


def main():
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise SystemExit(f"No rows found in {SOURCE}")

    total_titles = len(rows)
    total_files = sum(int(row["file_count"]) for row in rows)
    exact_ranked_rows = sorted(rows, key=lambda row: (-int(row["exact_hits"]), row["title_key"]))
    counts = [int(row["exact_hits"]) for row in exact_ranked_rows]
    total_hits = sum(counts)
    positive_titles = sum(value > 0 for value in counts)

    threshold_rows = []
    for k in K_VALUES:
        n = min(total_titles, math.ceil(total_titles * k / 100))
        covered = sum(counts[:n])
        result = {
            "top_k_percent": k,
            "selected_titles": n,
            "actual_titles_percent": round(n / total_titles * 100, 4),
            "cumulative_exact_hits": covered,
            "total_exact_hits": total_hits,
            "exact_coverage_percent": round(covered / total_hits * 100, 4),
        }
        threshold_rows.append(result)

    curve_rows = []
    cumulative = 0
    curve_rows.append({
        "top_k_titles": 0,
        "top_k_title_percent": 0.0,
        "cumulative_exact_hits": 0,
        "total_exact_hits": total_hits,
        "exact_coverage_percent": 0.0,
    })
    for k, hits in enumerate(counts, start=1):
        cumulative += hits
        curve_rows.append({
            "top_k_titles": k,
            "top_k_title_percent": round(k / total_titles * 100, 6),
            "cumulative_exact_hits": cumulative,
            "total_exact_hits": total_hits,
            "exact_coverage_percent": round(cumulative / total_hits * 100, 6) if total_hits else 0,
        })

    with POINTS_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        point_fields = [
            "top_k_titles", "top_k_title_percent", "cumulative_exact_hits",
            "total_exact_hits", "exact_coverage_percent",
        ]
        writer = csv.DictWriter(handle, fieldnames=point_fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(curve_rows)

    fields = [
        "top_k_percent", "selected_titles", "actual_titles_percent",
        "cumulative_exact_hits", "total_exact_hits", "exact_coverage_percent",
    ]
    with TABLE_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(threshold_rows)

    width, height = 1600, 810
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = find_font(34)
    body_font = find_font(19)
    axis_font = find_font(17)
    table_font = find_font(17)
    small_font = find_font(16)
    dark = (40, 40, 40)
    muted = (95, 95, 95)
    grid = (225, 225, 225)

    draw.text((75, 26), "王氏四种 exact 引文覆盖率", fill=dark, font=title_font)
    draw.text(
        (75, 78),
        f"{total_titles} 个规范书名；同标题只计一次，按 exact 命中降序",
        fill=muted, font=body_font,
    )

    left, top, right, bottom = 145, 160, 1430, 590
    x_at = lambda pct: left + (right - left) * pct / 100
    y_at = lambda pct: bottom - (bottom - top) * pct / 100
    max_title_hits = max(counts, default=0)
    raw_tick_step = max(1, math.ceil(max_title_hits / 5))
    tick_magnitude = 10 ** math.floor(math.log10(raw_tick_step))
    right_tick_step = math.ceil(raw_tick_step / tick_magnitude) * tick_magnitude
    right_axis_max = right_tick_step * 5
    right_axis_span = math.log1p(right_axis_max)
    right_ticks = [0]
    tick_magnitude = 1
    while tick_magnitude <= right_axis_max:
        right_ticks.extend(
            value
            for value in (tick_magnitude, 2 * tick_magnitude, 5 * tick_magnitude)
            if value <= right_axis_max
        )
        tick_magnitude *= 10
    if right_ticks[-1] != right_axis_max:
        while len(right_ticks) > 1:
            last_tick_y = math.log1p(right_ticks[-1]) / right_axis_span * (bottom - top)
            max_tick_y = bottom - top
            if max_tick_y - last_tick_y >= 22:
                break
            right_ticks.pop()
        right_ticks.append(right_axis_max)
    high_titles = math.ceil(total_titles * 0.10)
    middle_end = math.ceil(total_titles * 0.25)
    tier_bands = [
        (0, high_titles, f"高频 {high_titles}名", (240, 247, 252)),
        (high_titles, middle_end, f"中频 {middle_end - high_titles}名", (251, 247, 239)),
        (middle_end, total_titles, f"低频 {total_titles - middle_end}名", (246, 247, 248)),
    ]
    for start_rank, end_rank, _, color in tier_bands:
        x0 = round(x_at(start_rank / total_titles * 100))
        x1 = round(x_at(end_rank / total_titles * 100))
        draw.rectangle((x0, top, x1, bottom), fill=color)

    for tick in range(0, 101, 20):
        y = y_at(tick)
        x = x_at(tick)
        draw.line((left, y, right, y), fill=grid, width=1)
        draw.line((x, top, x, bottom), fill=grid, width=1)
        draw.text((left - 55, y - 10), str(tick), fill=muted, font=axis_font)
        centered_text(draw, x, bottom + 8, str(tick), axis_font, muted)
    draw.line((left, top, left, bottom), fill=(70, 70, 70), width=2)
    draw.line((right, top, right, bottom), fill=(70, 70, 70), width=2)
    draw.line((left, bottom, right, bottom), fill=(70, 70, 70), width=2)
    for value in right_ticks:
        y = bottom - math.log1p(value) / right_axis_span * (bottom - top)
        draw.line((right, y, right + 6, y), fill=ORANGE, width=1)
        draw.text((right + 9, y - 10), f"{value:,}", fill=ORANGE, font=axis_font)
    for rank_boundary in (high_titles, middle_end):
        x = round(x_at(rank_boundary / total_titles * 100))
        draw.line((x, top, x, bottom), fill=(155, 155, 155), width=1)
    draw.text((75, 105), "累计覆盖率 (%)", fill=muted, font=axis_font)
    centered_text(draw, (left + right) / 2, bottom + 36, "按 exact 命中排序的书名占全部规范书名比例 (%)", axis_font, muted)

    legend_y = 106
    draw.line((935, legend_y + 10, 973, legend_y + 10), fill=BLUE, width=4)
    draw.text((982, legend_y), "累计 exact 覆盖率", fill=dark, font=small_font)
    draw.line((1168, legend_y + 10, 1206, legend_y + 10), fill=ORANGE, width=4)
    draw.text((1215, legend_y), "第 k 名 exact hit 数", fill=dark, font=small_font)

    axis_label = "第 k 名 exact hit 数（对数式刻度）"
    axis_box = axis_font.getbbox(axis_label)
    axis_layer = Image.new(
        "RGBA",
        (axis_box[2] - axis_box[0] + 8, axis_box[3] - axis_box[1] + 8),
        (0, 0, 0, 0),
    )
    axis_draw = ImageDraw.Draw(axis_layer)
    axis_draw.text((4 - axis_box[0], 4 - axis_box[1]), axis_label, fill=ORANGE, font=axis_font)
    rotated_axis = axis_layer.rotate(90, expand=True)
    image.paste(rotated_axis, (1550, round((top + bottom - rotated_axis.height) / 2)), rotated_axis)

    for start_rank, end_rank, label, _ in tier_bands:
        center = (x_at(start_rank / total_titles * 100) + x_at(end_rank / total_titles * 100)) / 2
        centered_text(draw, center, 134, label, small_font, dark)

    points = [(x_at(0), y_at(0))]
    cumulative = 0
    for rank, hits in enumerate(counts, start=1):
        cumulative += hits
        points.append((x_at(rank / total_titles * 100), y_at(cumulative / total_hits * 100)))
    draw.line(points, fill=BLUE, width=4)
    per_title_hit_points = [
        (x_at(rank / total_titles * 100), bottom - math.log1p(hits) / right_axis_span * (bottom - top))
        for rank, hits in enumerate(counts, start=1)
    ]
    draw.line(per_title_hit_points, fill=ORANGE, width=3)

    # Compact exact-only lookup row beneath the curve.
    table_left, table_right = 75, 1525
    column_widths = [180, 150] + [160] * len(K_VALUES)
    edges = [table_left]
    for column_width in column_widths:
        edges.append(edges[-1] + column_width)
    heading_y, value_y = 690, 730
    draw.line((table_left, heading_y - 5, table_right, heading_y - 5), fill=(185, 185, 185), width=1)
    draw.line((table_left, heading_y + 30, table_right, heading_y + 30), fill=(210, 210, 210), width=1)
    headers = ["命中书名", "总 exact 命中"]
    for threshold in threshold_rows:
        headers.append(f"前{threshold['top_k_percent']}% ({threshold['selected_titles']}书名)")
    for index, header in enumerate(headers):
        centered_text(draw, (edges[index] + edges[index + 1]) / 2, heading_y, header, table_font, muted)

    values = [f"{positive_titles}/{total_titles}", f"{total_hits:,}"]
    values.extend(f"{threshold['exact_coverage_percent']:.2f}%" for threshold in threshold_rows)
    for index, value in enumerate(values):
        centered_text(draw, (edges[index] + edges[index + 1]) / 2, value_y, value, table_font, dark)

    draw.line((table_left, 780, table_right, 780), fill=(210, 210, 210), width=1)
    image.save(IMAGE_PATH)

    summary = {
        "source": str(SOURCE),
        "total_markdown_files": total_files,
        "unique_titles": total_titles,
        "exact_positive_titles": positive_titles,
        "exact_total_hits": total_hits,
        "thresholds": threshold_rows,
        "chart": str(IMAGE_PATH),
        "table": str(TABLE_PATH),
        "curve_points": str(POINTS_PATH),
        "curve_point_rows": len(curve_rows),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

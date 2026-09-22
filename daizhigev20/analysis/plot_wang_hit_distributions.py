from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
WANG_FILES = [
    ("读书杂志_王念孙", Path(r"D:\26大创\04-项目文献\A-原著原典\读书杂志_王念孙.md")),
    ("广雅疏证_王念孙", Path(r"D:\26大创\04-项目文献\A-原著原典\广雅疏证_王念孙.md")),
    ("经传释词_王引之", Path(r"D:\26大创\04-项目文献\A-原著原典\经传释词_王引之.md")),
    ("经义述闻_王引之", Path(r"D:\26大创\04-项目文献\A-原著原典\经义述闻_王引之.md")),
]

TRAD = str.maketrans({
    "説": "说", "說": "说", "廣": "广", "爾": "尔", "眾": "众", "衆": "众",
    "經": "经", "義": "义", "傳": "传", "書": "书", "禮": "礼", "學": "学",
    "醫": "医", "藥": "药", "黃": "黄", "國": "国", "漢": "汉", "後": "后",
    "與": "与", "為": "为", "爲": "为", "臺": "台", "從": "从", "於": "于",
    "見": "见", "會": "会", "寶": "宝", "圖": "图", "氣": "气", "標": "标",
    "體": "体", "聲": "声", "關": "关", "聞": "闻", "別": "别", "錄": "录",
    "録": "录", "點": "点", "號": "号", "劉": "刘", "華": "华", "龍": "龙",
    "門": "门", "東": "东", "車": "车", "馬": "马", "鳥": "鸟", "魚": "鱼",
    "獸": "兽", "蟲": "虫", "風": "风", "雲": "云", "異": "异", "詞": "词",
    "釋": "释", "辭": "辞", "類": "类", "續": "续", "補": "补", "訓": "训",
    "詁": "诂", "證": "证", "箋": "笺", "記": "记", "覽": "览", "羣": "群",
    "晉": "晋", "韓": "韩", "齊": "齐", "趙": "赵", "藝": "艺", "倉": "仓",
    "頡": "颉", "選": "选", "樂": "乐", "內": "内", "喪": "丧", "穀": "谷",
    "數": "数", "堯": "尧", "貢": "贡", "緇": "缁", "雜": "杂", "繫": "系",
    "鴻": "鸿", "術": "术", "農": "农", "齋": "斋", "賦": "赋", "紀": "纪",
    "韻": "韵", "館": "馆", "詩": "诗", "論": "论", "莊": "庄", "賈": "贾",
    "鈔": "钞", "問": "问", "開": "开", "占": "占", "縣": "县", "濟": "济",
    "榮": "荣", "條": "条", "敘": "叙", "獨": "独", "衛": "卫", "師": "师",
    "軍": "军", "無": "无",
})

PUNCT_RE = re.compile(r"[\s_\-—–·•．・/\\、，,。:：;；（）()【】\[\]<>〈〉《》“”\"'‘’]")
CITATION_RE = re.compile(r"[《〈](.{1,120}?)[》〉]")

WEAK_WORDS = {"序", "传", "注", "疏", "志", "书", "礼", "易", "诗", "史", "文", "集", "本", "记", "论", "说", "卷", "篇", "部"}


def compact(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(TRAD).casefold()
    return PUNCT_RE.sub("", value)


def citation_forms(inner: str) -> set[str]:
    inner = re.sub(r"\s+", "", inner).strip()
    forms = {compact(inner)}
    for separator in ("·", "•", "．", "・", ":", "："):
        if separator in inner:
            parts = [part for part in inner.split(separator) if part]
            forms.update(compact(part) for part in parts)
            forms.add(compact(inner.split(separator, 1)[0]))
    return {form for form in forms if form}


def query_aliases(stem: str) -> tuple[set[str], set[str]]:
    """Return (explicit family aliases, weak aliases) for one filename."""
    main = re.split(r"[_（(]", stem, maxsplit=1)[0]
    main = re.split(r"[-—]", main, maxsplit=1)[0]
    strong: set[str] = set()
    weak: set[str] = set()

    manual = {
        "说文解字": ["说文"],
        "说文解字注": ["说文"],
        "重修玉篇": ["玉篇"],
        "原本广韵": ["广韵"],
        "重修广韵": ["广韵"],
        "黄帝内经素问": ["素问"],
        "神农本草经": ["神农本草"],
        "名医别录": ["名医别录"],
        "经典释文": ["释文"],
        "春秋左传": ["左传"],
        "春秋左传注疏": ["左传"],
        "春秋左传正义": ["左传"],
        "春秋左氏传补注": ["左传"],
        "左传附注": ["左传"],
        "春秋公羊传": ["公羊传"],
        "春秋公羊传注疏": ["公羊传"],
        "春秋谷梁传": ["谷梁传"],
        "春秋穀梁传注疏": ["谷梁传"],
        "吕氏春秋集解": ["吕氏春秋"],
        "群书治要六韬": ["群书治要"],
        "文选注": ["文选"],
        "大戴礼记": ["大戴礼"],
    }
    for alias in manual.get(main, []):
        strong.add(compact(alias))

    if main.startswith("春秋") and len(main) > 2:
        weak.add(compact("春秋"))
    if main in {"说文", "尔雅", "广雅", "方言", "玉篇", "广韵", "集韵", "素问"}:
        strong.add(compact(main))
    for word in WEAK_WORDS:
        if compact(main) == compact(word):
            weak.add(compact(word))
    return strong, weak


def find_font(size: int):
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def event_matches(record, forms: set[str]) -> tuple[str | None, str | None]:
    if record["exact"] in forms:
        return "exact", record["exact"]
    for alias in record["strong_aliases"]:
        if alias in forms or any(alias in form for form in forms):
            return "family", alias
    for alias in record["weak_aliases"]:
        if alias in forms or any(alias in form for form in forms):
            return "weak", alias
    return None, None


def draw_histogram(rows: list[dict], path: Path):
    bins = [(0, 0), (1, 1), (2, 2), (3, 5), (6, 10), (11, 20), (21, 50), (51, 100), (101, 200), (201, 500), (501, 1000), (1001, None)]
    labels = ["0", "1", "2", "3–5", "6–10", "11–20", "21–50", "51–\n100", "101–\n200", "201–\n500", "501–\n1000", "1001+"]

    def counts(key):
        output = []
        for low, high in bins:
            if high is None:
                output.append(sum(row[key] >= low for row in rows))
            else:
                output.append(sum(low <= row[key] <= high for row in rows))
        return output

    exact = counts("exact_hits")
    any_hits = counts("any_hits")
    width, height = 1700, 850
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = find_font(34)
    label_font = find_font(21)
    small_font = find_font(18)
    draw.text((70, 28), "王氏四种外部文献命中次数分布（同标题只计一次）", fill=(35, 35, 35), font=title_font)
    draw.text((70, 78), "按规范书名去重；横轴为该书名的命中次数区间，纵轴为书名数；exact 与 any-match 使用同一批书名", fill=(90, 90, 90), font=small_font)

    panels = [(70, 145, 790, 825, "exact name", exact, (44, 104, 173)), (900, 145, 1620, 825, "any match", any_hits, (218, 119, 46))]
    max_count = max(exact + any_hits + [1])
    for left, top, right, bottom, panel_title, values, color in panels:
        draw.text((left, top), panel_title, fill=color, font=label_font)
        plot_left, plot_right = left + 70, right - 20
        plot_top, plot_bottom = top + 50, bottom - 100
        draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill=(70, 70, 70), width=2)
        draw.line((plot_left, plot_top, plot_left, plot_bottom), fill=(70, 70, 70), width=2)
        for tick in range(0, max_count + 1, max(1, int(math.ceil(max_count / 5)))):
            y = plot_bottom - (plot_bottom - plot_top) * tick / max_count
            draw.line((plot_left, y, plot_right, y), fill=(225, 225, 225), width=1)
            draw.text((left + 4, y - 10), str(tick), fill=(90, 90, 90), font=small_font)
        slot = (plot_right - plot_left) / len(values)
        for index, value in enumerate(values):
            x0 = plot_left + index * slot + slot * 0.12
            x1 = plot_left + (index + 1) * slot - slot * 0.12
            y1 = plot_bottom - (plot_bottom - plot_top) * value / max_count
            draw.rectangle((x0, y1, x1, plot_bottom), fill=color)
            value_text = str(value)
            value_box = draw.textbbox((0, 0), value_text, font=small_font)
            value_width = value_box[2] - value_box[0]
            value_y = max(plot_top - 25, y1 - 28)
            draw.text(((x0 + x1) / 2 - value_width / 2, value_y), value_text, fill=(45, 45, 45), font=small_font)

            center_x = plot_left + (index + 0.5) * slot
            for line_no, line in enumerate(labels[index].split("\n")):
                label_box = draw.textbbox((0, 0), line, font=small_font)
                label_width = label_box[2] - label_box[0]
                draw.text((center_x - label_width / 2, plot_bottom + 7 + line_no * 22), line, fill=(70, 70, 70), font=small_font)
        draw.text((left + 4, plot_top - 28), "书名数", fill=(80, 80, 80), font=small_font)
    image.save(path)


def draw_rank(rows: list[dict], path: Path):
    width, height = 1500, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = find_font(34)
    label_font = find_font(21)
    small_font = find_font(18)
    draw.text((70, 35), "王氏四种命中次数排名曲线（同标题只计一次）", fill=(35, 35, 35), font=title_font)
    draw.text((70, 82), "对数坐标用于观察长尾；每个点对应一个规范书名，exact 与 any-match 分别排序", fill=(90, 90, 90), font=small_font)
    left, top, right, bottom = 110, 150, 1430, 800
    draw.line((left, bottom, right, bottom), fill=(70, 70, 70), width=2)
    draw.line((left, top, left, bottom), fill=(70, 70, 70), width=2)
    positives = {}
    for key in ("exact_hits", "any_hits"):
        values = sorted((row[key] for row in rows if row[key] > 0), reverse=True)
        positives[key] = values
    max_x = max([len(v) for v in positives.values()] + [1])
    max_y = max([max(v) for v in positives.values() if v] + [1])
    def sx(rank):
        return left + (right - left) * math.log10(max(rank, 1)) / math.log10(max(max_x, 1))
    def sy(value):
        return bottom - (bottom - top) * math.log10(max(value, 1)) / math.log10(max(max_y, 1))
    for tick in (1, 10, 100, 1000, 10000):
        if tick <= max_y:
            y = sy(tick)
            draw.line((left, y, right, y), fill=(230, 230, 230), width=1)
            draw.text((55, y - 9), str(tick), fill=(80, 80, 80), font=small_font)
    for key, color, label in (("exact_hits", (44, 104, 173), "exact name"), ("any_hits", (218, 119, 46), "any match")):
        points = [(sx(i + 1), sy(value)) for i, value in enumerate(positives[key])]
        if len(points) >= 2:
            draw.line(points, fill=color, width=4)
        legend_x = 1040 if key == "exact_hits" else 1220
        draw.line((legend_x, 105, legend_x + 35, 105), fill=color, width=4)
        draw.text((legend_x + 45, 94), label, fill=(60, 60, 60), font=small_font)
    draw.text((right - 180, bottom + 22), "书名排名（log）", fill=(80, 80, 80), font=small_font)
    draw.text((left - 5, top - 30), "命中次数（log）", fill=(80, 80, 80), font=small_font)
    image.save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    literature = []
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if relative.parts and relative.parts[0] == ".sources":
            continue
        if str(relative) in {"README.md", "FONTS.md"}:
            continue
        literature.append(path)

    title_records = {}
    for path in sorted(literature, key=lambda item: item.as_posix().casefold()):
        strong_aliases, weak_aliases = query_aliases(path.stem)
        canonical_stem = re.split(r"[_（(]", path.stem, maxsplit=1)[0]
        title_key = compact(canonical_stem)
        record = title_records.get(title_key)
        if record is None:
            record = {
                "title_key": title_key,
                "title": canonical_stem,
                "files": [],
                "exact": title_key,
                "strong_aliases": set(),
                "weak_aliases": set(),
                "exact_hits": 0,
                "family_hits": 0,
                "weak_hits": 0,
                "any_hits": 0,
                "exact_works": set(),
                "any_works": set(),
                "examples": [],
            }
            title_records[title_key] = record
        record["files"].append(path.relative_to(ROOT).as_posix())
        record["strong_aliases"].update(strong_aliases)
        record["weak_aliases"].update(weak_aliases)

    records = list(title_records.values())

    for work_name, path in WANG_FILES:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            for match in CITATION_RE.finditer(line):
                inner = match.group(1)
                forms = citation_forms(inner)
                for record in records:
                    kind, alias = event_matches(record, forms)
                    if kind is None:
                        continue
                    record["any_hits"] += 1
                    record["any_works"].add(work_name)
                    if kind == "exact":
                        record["exact_hits"] += 1
                        record["exact_works"].add(work_name)
                    elif kind == "family":
                        record["family_hits"] += 1
                    else:
                        record["weak_hits"] += 1
                    if len(record["examples"]) < 3:
                        record["examples"].append(f"{work_name}:{line_no}:{inner}")

    for record in records:
        record["files"].sort(key=str.casefold)
        record["file_count"] = len(record["files"])
        record["files"] = " | ".join(record["files"])
        record["exact_works"] = sorted(record["exact_works"])
        record["any_works"] = sorted(record["any_works"])
        record["examples"] = " | ".join(record["examples"])
        record.pop("strong_aliases", None)
        record.pop("weak_aliases", None)
        record.pop("exact", None)

    ordered_records = sorted(records, key=lambda item: item["title_key"])
    with (OUT / "wang_hit_matrix.tsv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["title_key", "title", "file_count", "files", "exact_hits", "family_hits", "weak_hits", "any_hits", "exact_works", "any_works", "examples"]
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for record in ordered_records:
            row = dict(record)
            row["exact_works"] = ",".join(row["exact_works"])
            row["any_works"] = ",".join(row["any_works"])
            writer.writerow(row)

    with (OUT / "wang_duplicate_title_files.tsv").open("w", encoding="utf-8-sig", newline="") as handle:
        duplicate_fields = ["title", "title_key", "file_count", "exact_hits_once", "any_hits_once", "files"]
        writer = csv.DictWriter(handle, fieldnames=duplicate_fields, delimiter="\t")
        writer.writeheader()
        for record in ordered_records:
            if record["file_count"] > 1:
                writer.writerow({
                    "title": record["title"],
                    "title_key": record["title_key"],
                    "file_count": record["file_count"],
                    "exact_hits_once": record["exact_hits"],
                    "any_hits_once": record["any_hits"],
                    "files": record["files"],
                })

    bins = [(0, 0), (1, 1), (2, 2), (3, 5), (6, 10), (11, 20), (21, 50), (51, 100), (101, 200), (201, 500), (501, 1000), (1001, None)]
    labels = ["0", "1", "2", "3–5", "6–10", "11–20", "21–50", "51–100", "101–200", "201–500", "501–1000", "1001+"]
    summary_rows = []
    for label, key in (("exact name", "exact_hits"), ("any match", "any_hits")):
        for bin_label, (low, high) in zip(labels, bins):
            count = sum((value := record[key]) >= low and (high is None or value <= high) for record in records)
            summary_rows.append({"metric": label, "bin": bin_label, "title_count": count})
    with (OUT / "wang_hit_distribution_summary.tsv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "bin", "title_count"], delimiter="\t")
        writer.writeheader()
        writer.writerows(summary_rows)

    overview = {
        "root": str(ROOT),
        "literature_markdown_files": len(literature),
        "unique_title_count": len(records),
        "exact_positive_titles": sum(record["exact_hits"] > 0 for record in records),
        "any_positive_titles": sum(record["any_hits"] > 0 for record in records),
        "exact_event_count": sum(record["exact_hits"] for record in records),
        "any_event_count": sum(record["any_hits"] for record in records),
        "max_exact_hits": max((record["exact_hits"] for record in records), default=0),
        "max_any_hits": max((record["any_hits"] for record in records), default=0),
    }
    (OUT / "wang_hit_distribution_overview.json").write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    draw_histogram(records, OUT / "wang_hit_count_distribution.png")
    draw_rank(records, OUT / "wang_hit_count_rank.png")
    print(json.dumps(overview, ensure_ascii=False))


if __name__ == "__main__":
    main()

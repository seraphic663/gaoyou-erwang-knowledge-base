# -*- coding: utf-8 -*-
"""
bulk_importer.py — 批量导入 parsed_data.py 数据到 SQLite
用法：
  python bulk_importer.py          # 完整导入（重建数据库）
  python bulk_importer.py --dry-run  # 仅打印统计，不写入
"""
import sys, json, re, argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ── 加载 parsed_data.py ───────────────────────────────────────────────
PF = Path(__file__).parent / "parsed_data.py"
if not PF.exists():
    sys.exit("[ERROR] parsed_data.py not found. Run parser.py first.")
_ns = {}
with open(PF, encoding="utf-8") as f:
    exec(f.read(), _ns)
WORKS     = _ns.get("WORKS", [])
TERMS_DEF = _ns.get("TERMS_DEF", [])
EVIDENCES = _ns.get("EVIDENCES_DEF", [])
SKIP_LOG  = _ns.get("SKIP_LOG", [])

# ── DB ────────────────────────────────────────────────────────────────
import database

EV_TYPE_MAP = {
    "书证": "书证", "声训": "声训", "义证": "义证",
    "音训": "声训", "语法证据": "语法证据", "异文": "异文",
    "形证": "形证", "其他": "书证",
}
_CHAP_TO_WORK = {
    "皋陶謨": "尚书", "禹貢": "尚书", "盤庚": "尚书", "伊訓": "尚书",
    "夏本紀": "史记", "魯頌": "毛诗", "魯頌·駉篇": "毛诗",
    "說卦傳": "易经", "繫辭傳": "易经", "序卦傳": "易经", "雜卦傳": "易经",
    "文言傳": "易经", "大雅": "毛诗", "小雅": "毛诗", "邶風": "毛诗",
    "衛風": "毛诗", "鄭風": "毛诗", "商頌": "毛诗", "秦風": "毛诗",
    "唐風": "毛诗", "齊風": "毛诗", "周頌": "毛诗",
    "禮運": "礼记", "大學": "大学", "中庸": "中庸",
    "祭法": "礼记", "禮器": "礼记", "檀弓": "礼记",
    "周官": "周礼", "周官·樂師": "周礼", "考工記": "考工记",
    "左傳": "左传", "公羊傳": "公羊传", "穀梁傳": "谷梁传",
    "呂氏春秋": "吕氏春秋", "莊子": "庄子", "老子": "老子",
    "墨子": "墨子", "韓非子": "韩非子", "管子": "管子",
    "史記": "史记", "太史公自序": "史记",
    "漢書": "汉书", "後漢書": "后汉书",
    "國語": "国语", "晉語": "国语", "齊語": "国语",
    "戰國策": "战国策", "孟子": "孟子",
    "說文": "说文解字", "方言": "方言", "爾雅": "尔雅",
    "楚辭": "楚辞", "九章": "楚辞",
    "廣雅": "广雅", "廣雅疏證": "广雅疏证",
    "白虎通義": "白虎通义", "春秋繁露": "春秋繁露",
    "說苑": "说苑", "論衡": "论衡", "鹽鐵論": "盐铁论",
    "淮南子": "淮南子", "韓詩": "韩诗", "文選": "文选",
    "玉篇": "玉篇", "廣韻": "广韵", "三蒼": "三苍",
    "藝文類聚": "艺文类聚", "太玄": "太玄",
    "晏子春秋": "晏子春秋", "風俗通義": "风俗通义",
    "新序": "新序", "賈子": "贾子", "法言": "法言", "逸周書": "逸周书",
}


def ev_type(t):
    return EV_TYPE_MAP.get(t.strip(), "书证")


def resolve_work(title, wmap):
    if not title:
        return wmap.get("广雅疏证", 1)
    if title in wmap:
        return wmap[title]
    for chap, book in _CHAP_TO_WORK.items():
        if chap in title:
            wid = wmap.get(book)
            if wid:
                return wid
    book = title.split("·")[0].strip("《》")
    if book in wmap:
        return wmap[book]
    if len(book) >= 2:
        for w, wid in wmap.items():
            if w.startswith(book[:2]):
                return wid
    return wmap.get("广雅疏证", 1)


def extract_gloss(cm):
    if not cm:
        return ""
    m = re.search(r"训[「『]?([\u4e00-\u9fff]{1,4})", cm)
    if m:
        return m.group(1)
    m = re.search(r"([\u4e00-\u9fff])也", cm)
    if m:
        return m.group(1)
    return ""


def import_all(dry=False):
    print("=" * 50)
    print("  bulk_importer")
    print("=" * 50)
    print(f"  WORKS:     {len(WORKS)}")
    print(f"  TERMS:     {len(TERMS_DEF)}")
    print(f"  EVIDENCES: {len(EVIDENCES)}")
    print(f"  SKIP_LOG:  {len(SKIP_LOG)}")
    print()

    if not dry:
        print("[1/5] Reset DB...")
        database.reset()

    # ── 2. WORKS ──────────────────────────────────────────────
    wmap = {}
    print(f"[2/5] WORKS ({len(WORKS)})...")
    for row in WORKS:
        if len(row) < 2:
            continue
        title = row[1]
        author = row[2] if len(row) > 2 else ""
        wtype  = row[3] if len(row) > 3 else "原始经典"
        dynasty = row[4] if len(row) > 4 else ""
        tnote  = row[5] if len(row) > 5 else ""
        notes  = row[6] if len(row) > 6 else ""
        if not title:
            continue
        if dry:
            print(f"  work: {title}")
        else:
            wid = database.upsert_work(title, author, wtype, dynasty, tnote, notes)
            wmap[title] = wid
            if row[0]:
                wmap[str(row[0])] = wid
    print(f"  -> {len(wmap)} works")

    # ── 3. TERMS ───────────────────────────────────────────────
    tmap = {}
    print(f"[3/5] TERMS ({len(TERMS_DEF)})...")
    bad_t = 0
    for row in TERMS_DEF:
        if not row or len(row) < 6:
            bad_t += 1
            continue
        term = row[0]
        ttype = row[1]
        cat   = row[2]
        als   = row[3]
        cm    = row[4]
        notes = row[5]
        if not term:
            bad_t += 1
            continue
        if ttype not in ("术语", "词", "字"):
            ttype = "词"
        if dry:
            if len(tmap) < 3:
                print(f"  term: {term} type={ttype} cat={cat}")
        else:
            try:
                tid = database.insert_term(
                    term=term, term_type=ttype,
                    category=cat or "同义实词",
                    aliases=als if isinstance(als, list) else [],
                    notes=notes or "", core_meaning=cm or "",
                )
                tmap[term] = tid
            except Exception:
                rows = database.search_terms(term, limit=1)
                if rows:
                    tmap[term] = rows[0]["id"]
    print(f"  -> {len(tmap)} terms (bad: {bad_t})")

    # ── 4. CASES（按 line_no + gloss 唯一确定，不合并同名 gloss）──
    # 从 EVIDENCES_DEF 的注释中解析行号，构建 (line_no, gloss) → case_id 映射
    # 从 EVIDENCES_DEF 源码注释中解析行号和 gloss
    ev_meta: dict[tuple, str] = {}  # (term_char, line_no) → gloss
    ev_src_lines: list = []
    ev_start_found = False
    pf_src = open(Path(__file__).parent / "parsed_data.py", encoding="utf-8")
    for raw_line in pf_src:
        if "EVIDENCES_DEF = [" in raw_line:
            ev_start_found = True
        if not ev_start_found:
            continue
        m = re.match(r'\s*# ── (.+?)（行 (\d+)）\s+「(.+?)也」', raw_line)
        if m:
            ev_src_lines.append((m.group(1), int(m.group(2)), m.group(3)))

    pf_src.close()
    for (tc, ln, gloss) in ev_src_lines:
        ev_meta[(tc, ln)] = gloss

    # 按 (line_no, gloss) 分组构建 cases
    entry_key_terms: dict[tuple, list] = {}  # (line_no, gloss) → [term_chars]
    for (tc, ln), gloss in ev_meta.items():
        entry_key_terms.setdefault((ln, gloss), []).append(tc)

    gcid = {}
    ncases = 0
    for (line_no, gloss) in sorted(entry_key_terms.keys(), key=lambda x: x[0]):
        chars = entry_key_terms[(line_no, gloss)]
        tids = [tmap[c] for c in chars if c in tmap]
        if not tids:
            continue
        gloss_title = f"广雅疏证「{gloss}也」词条群（行{line_no}）"
        gloss_problem = f"疏通「{gloss}也」诸字之义例、声训、通假、书证"
        gloss_conclusion = f"以上诸字均有「{gloss}」义，可由文献、声训、通假互证成立。"
        if dry:
            print(f"  case: line={line_no} gloss={gloss} terms={len(tids)}")
        else:
            cid = database.insert_case(
                title=gloss_title, section_title="释诂",
                volume_title="广雅疏证卷第一上", term_ids=tids,
                problem=gloss_problem,
                method="声训、通假、书证、义证、语法对文",
                conclusion=gloss_conclusion,
                certainty="确定", status="草稿",
            )
            gcid[(line_no, gloss)] = cid
            for tc in chars:
                tid = tmap.get(tc)
                if not tid:
                    continue
                ex = database.get_term_by_id(tid)
                if not ex:
                    continue
                try:
                    cids = json.loads(ex.get("case_ids", "[]"))
                except Exception:
                    cids = []
                if cid not in cids:
                    cids.append(cid)
                    database.update_term_case_ids(tid, cids)
        ncases += 1
    print(f"  -> {ncases} cases")

    # ── 5. EVIDENCES ─────────────────────────────────────────
    print(f"[5/5] EVIDENCES ({len(EVIDENCES)})...")
    ev_ok = ev_bad = 0
    for row in EVIDENCES:
        if not row or len(row) < 6:
            ev_bad += 1
            continue
        tc   = row[0]
        et   = ev_type(row[1])
        wtitle = row[2]
        qt   = (row[3] or "")[:500]
        cs   = (row[4] or "")[:200]
        note = (row[5] or "")[:200]
        # row[6] 是 line_no（新增字段，parser.py 写入）
        ev_line_no = row[6] if len(row) > 6 else 0
        # 从 entry_key_terms 找该行(ln, gloss)对应的 case_id
        key_cid = None
        for (ln, gloss), chars in entry_key_terms.items():
            if ln == ev_line_no and tc in chars:
                key_cid = gcid.get((ln, gloss))
                break
        tid = tmap.get(tc)
        if not tid:
            ev_bad += 1
            continue
        cid = key_cid
        wid = resolve_work(wtitle, wmap)
        if dry:
            ev_ok += 1
            continue
        try:
            database.insert_evidence(
                case_id=cid, term_id=tid, evidence_type=et,
                work_id=wid, quote_text=qt,
                core_snippet=cs, note=note,
            )
            ev_ok += 1
        except Exception:
            ev_bad += 1
    print(f"  -> {ev_ok} inserted (bad: {ev_bad})")

    st = database.stats()
    print()
    print("=" * 50)
    print("  DONE")
    print(f"  works:      {st['work_count']}")
    print(f"  terms:      {st['term_count']}")
    print(f"  cases:      {st['case_count']}")
    print(f"  evidences:  {st['evidence_count']}")
    print(f"  SKIP_LOG:   {len(SKIP_LOG)} (not imported)")
    print("=" * 50)
    return st


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    import_all(dry=p.parse_args().dry_run)

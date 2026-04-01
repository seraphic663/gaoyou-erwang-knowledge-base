"""
data_importer.py — 《廣雅疏證》「始也」条数据录入脚本

用法：
  python data_importer.py          # 完整录入（重建数据库）
  python data_importer.py --reset   # 同上（重建数据库）
  python data_importer.py --dry-run # 仅打印 SQL，不写入

数据来源：source.txt + A方案数据库录入表（手工提炼）

录入内容：
  - 15 部典籍（works）
  - 1 条二王论述段落（passages）
  - 20 个词条（terms）+ 1 个核心术语（terms）
  - 1 个考据案例（cases）
  - 22 条证据（evidences，每条精确关联到字）
"""

import sys
import argparse
import json
from pathlib import Path

import db2


# ─── 数据定义 ────────────────────────────────────────────────────────────────

WORKS = [
    # id, title, author, work_type, dynasty, time_note, notes
    (1,  "广雅疏证",    "王念孙、王引之",  "二王著作",  "清",
     "清乾隆—嘉庆",    "卷第一上·释诂「始也」条"),
    (2,  "广雅",        "张揖",            "原始经典",  "三国·魏",
     "曹魏",           "释诂·始也"),
    (3,  "毛诗",        "毛亨、毛苌",      "原始经典",  "西汉",
     "西汉",           "鲁颂·駉篇 毛传"),
    (4,  "尚书",        "先秦史官",        "原始经典",  "先秦",
     "先秦",           "皋陶谟、禹贡、盘庚、伊训"),
    (5,  "礼记",        "戴圣",            "原始经典",  "西汉",
     "西汉",           "礼运"),
    (6,  "方言",        "扬雄",            "原始经典",  "西汉",
     "西汉",           "卷一 始也"),
    (7,  "说文解字",    "许慎",            "原始经典",  "东汉",
     "东汉",           "肁、自 字条"),
    (8,  "孟子",        "孟轲",            "原始经典",  "战国",
     "战国",           "万章篇"),
    (9,  "吕氏春秋",    "吕不韦门客",      "原始经典",  "战国末",
     "战国末",         "大乐篇 高诱注"),
    (10, "周礼",        "周公及后人",      "原始经典",  "西周—汉",
     "西周至汉",       "乐师"),
    (11, "庄子",        "庄周",            "原始经典",  "战国",
     "战国",           "天地篇、秋水篇"),
    (12, "国语",        "左丘明",          "原始经典",  "春秋",
     "春秋",           "齐语"),
    (13, "史记",        "司马迁",          "原始经典",  "西汉",
     "西汉",           "夏本纪、太史公自序"),
    (14, "汉书",        "班固",            "原始经典",  "东汉",
     "东汉",           "扬雄传"),
    (15, "楚辞",        "屈原、宋玉",       "原始经典",  "战国",
     "战国",           "九章 王逸注"),
]

# 广雅原文（字头行）
GUANGYA_HEAD = "古、昔、先、創、方、作、造、朔、萌、芽、本、根、櫱、鼃、戶瓜反 䔞、律 昌、孟、鼻、業，始也。"

# 二王论述完整段落（按行拆分，便于对证）
ERWANG_PARAGRAPHS = [
    "古、昔、先、創、方、作、造、朔、萌、芽、本、根、櫱、鼃、戶瓜反 䔞、律 昌、孟、鼻、業，始也。",
    "作者，《魯頌·駉篇》'思馬斯作'，毛傳云：'作，始也。' '作'之言'乍'也。'乍'亦'始'也。《皋陶謨》'烝民乃粒，萬邦作乂'，'作'與'乃'相對成文。言烝民乃粒，萬邦始乂也。《禹貢》'萊夷作牧'，言萊夷水始放牧也。'沱潛既道，雲夢土作乂'，'作'與'既'相對成文，言沱潛之水既道，雲夢之土始乂也。《夏本紀》皆以'爲'字代之，於文義稍疏矣。",
    "造者，高誘注《呂氏春秋·大樂篇》云：'造，始也。'《孟子·萬章篇》引《伊訓》云：'天誅造攻自牧宮。'",
    "朔者，《禮運》云：'皆從其初，皆從其朔。'",
    "櫱與萌芽同義。《盤庚》云：'若顛木之有由櫱。'芽米謂之櫱，災始生謂之孼，義並與'櫱'同。",
    "鼃、䔞者，《方言》: '鼃、律，始也。' '律'與'䔞'通。《說文》：'肁，始開也。從户聿。' '聿'亦始也，聲與'䔞'近而義同。凡事之始即爲事之法，故始謂之方，亦謂之律，法謂之律，亦謂之方矣。",
    '昌，讀爲\u2018倡和\u2019之\u2018倡\u2019。王逸注《九章》云：\u2018倡，始也。\u2019《周官·樂師》\u2018教愷歌，遂倡之\u2019，鄭注云：\u2018故書「倡」爲「昌」。\u2019是\u2018昌\u2019與\u2018倡\u2019通。',
    "'鼻'之言'自'也。《說文》：'自，始也'，'讀若鼻，今俗以始生子爲鼻子，是。'《方言》：'鼻，始也。嘼之初生謂之鼻，人之初生謂之首。'《莊子·天地篇》'誰其比憂'，'比'，司馬彪本作'鼻'，云：'始也。'《漢書·揚雄傳》'或鼻祖於汾隅'劉德注亦云：'鼻，始也。'",
    "業與基同義，故亦訓爲始。《齊語》'擇其善者而業用之'，韋昭注云：'業猶創也。' 〔《莊子•秋水篇》云：'將忘子之故，失子之業。'〕《史記·太史公自序》云：'項梁業之，子羽接之。'",
    "【補正】",
    "'業猶創也'下補：《莊子·秋水篇》云：'將忘子之故，失子之業。'",
]

ERWANG_FULL_TEXT = "\n".join(ERWANG_PARAGRAPHS)

# 词条定义：(term, term_type, category, aliases, core_meaning, notes)
TERMS_DEF = [
    # 0  核心术语
    ("始",  "术语", "训诂·同义词群", ["初", "基", "創", "乍", "肇"],
     "「始」为训诂核心词，本组二十字皆训为「始」。",
     "广雅释诂「始也」词条群核心词"),
    # 1  同义实词
    ("古",  "词", "同义实词", [],
     "「古」训「始」，指时间之初。",
     "训「始」"),
    ("昔",  "词", "同义实词", [],
     "「昔」训「始」，指往昔之初。",
     "训「始」"),
    ("先",  "词", "同义实词", [],
     "「先」训「始」，指次序之始。",
     "训「始」"),
    ("創",  "词", "同义实词", ["创"],
     "「創」训「始」，指开创之初。",
     "训「始」"),
    ("方",  "词", "同义实词", [],
     "「方」训「始」，凡事之始即为之法，故始谓之方。",
     "训「始」，与「律」对文互训"),
    ("作",  "词", "同义实词", ["乍"],
     "「作」训「始」，'作'之言'乍'也，乍亦始也。",
     "训「始」，声训为乍"),
    ("造",  "词", "同义实词", [],
     "「造」训「始」，高诱注《吕氏春秋》云：'造，始也。'",
     "训「始」"),
    ("朔",  "词", "同义实词", [],
     "「朔」训「始」，《礼运》：'皆从其朔。'",
     "训「始」"),
    ("萌",  "词", "同义实词", [],
     "「萌」训「始」，与萌芽同义。",
     "训「始」"),
    ("芽",  "词", "同义实词", [],
     "「芽」训「始」，与萌芽同义。",
     "训「始」"),
    ("本",  "词", "同义实词", [],
     "「本」训「始」，根本为本源之始。",
     "训「始」"),
    ("根",  "词", "同义实词", [],
     "「根」训「始」，根为本始之处。",
     "训「始」"),
    ("櫱",  "词", "同义实词", ["蘖", "孼"],
     "「櫱」训「始」，《盘庚》：'若颠木之有由櫱。'芽米谓之櫱，灾始生谓之孼。",
     "训「始」，与萌芽同义"),
    # 15  通假/方言字
    ("鼃",  "字", "通假/方言字", [],
     "「鼃」训「始」，《方言》：'鼃、律，始也。'",
     "训「始」"),
    # 16  通假/方言字
    ("䔞",  "字", "通假/方言字", ["律"],
     "「䔞」训「始」，与「律」通，'律'与'䔞'通。",
     "训「始」"),
    ("律",  "词", "同义实词", ["䔞"],
     "「律」训「始」，与「䔞」通，凡事之始即为之法。",
     "训「始」，与「方」对文互训"),
    # 18  通假字
    ("昌",  "词", "通假字", ["倡"],
     "「昌」读为「倡」，'倡，始也。'昌与倡通。",
     "训「始」，音训为倡"),
    # 19  同义实词
    ("孟",  "词", "同义实词", [],
     "「孟」训「始」，指兄弟排行之首。",
     "训「始」"),
    # 20  方言实词
    ("鼻",  "词", "方言实词", ["自"],
     "「鼻」之言「自」也，《说文》：'自，始也，读若鼻。'",
     "训「始」，声训为自"),
    # 21  同义实词
    ("業",  "词", "同义实词", ["业"],
     "「業」与「基」同义，训为始，《齐语》韦昭注：'業犹创也。'",
     "训「始」"),
]

# 案例
CASE_DEF = dict(
    title      = "广雅疏证「始也」词条群考证",
    section_title = "释诂",
    volume_title  = "广雅疏证卷第一上",
    problem    = ("疏通古、昔、先、創、方、作、造、朔、萌、芽、本、根、"
                 "櫱、鼃、䔞、律、昌、孟、鼻、業诸字俱训「始」之义例、"
                 "声训、通假、书证"),
    method     = "声训、通假、书证、义证、语法对文",
    process_text = ERWANG_FULL_TEXT,
    conclusion = "以上诸字均有「始」义，可由文献、声训、通假互证成立。",
    certainty  = "确定",
    status     = "已校对",
)

# 证据定义
# (term_char, evidence_type, work_title, quote_text, core_snippet, note)
# core_snippet = 对该字而言最关键的一两句话
EVIDENCES_DEF = [
    # 作（id=7）
    ("作", "书证",   "毛诗",
     "《鲁颂·駉篇》'思马斯作'，毛传：'作，始也。'",
     "毛传：'作，始也。'",
     "证「作」训始，毛传为关键书证"),
    ("作", "声训",   "广雅疏证",
     "'作'之言'乍'也，'乍'亦'始'也。",
     "'作'之言'乍'也，乍亦始也。",
     "声训互证"),
    ("作", "语法证据", "尚书",
     "《皋陶谟》：'烝民乃粒，万邦作乂。' '作'与'乃'相对成文。",
     "'作'与'乃'相对成文，言万邦始乂。",
     "语法对文证"),
    ("作", "书证",   "尚书",
     "《禹贡》：'莱夷作牧。'",
     "言莱夷水始放牧。",
     "证「作」训始"),
    ("作", "语法证据", "尚书",
     "《禹贡》：'沱潜水既道，雲梦土作乂。' '作'与'既'相对成文。",
     "'作'与'既'相对成文，言雲梦土始乂。",
     "语法对文证"),
    ("作", "异文",   "史记",
     "《夏本纪》皆以'为'字代'作'，于文义稍疏。",
     "《夏本纪》以'为'代'作'，文义稍疏。",
     "校勘异文"),

    # 造（id=8）
    ("造", "书证",   "吕氏春秋",
     "高诱注《吕氏春秋·大乐篇》云：'造，始也。'",
     "高诱注：'造，始也。'",
     "证「造」训始"),
    ("造", "书证",   "尚书",
     "《孟子·万章篇》引《伊训》：'天诛造攻自牧宫。'",
     "《伊训》：'天诛造攻自牧宫。'",
     "证「造」训始"),

    # 朔（id=9）
    ("朔", "书证",   "礼记",
     "《礼运》：'皆从其初，皆从其朔。'",
     "'皆从其朔。'",
     "证「朔」训始"),

    # 櫱（id=14）
    ("櫱", "书证",   "尚书",
     "《盘庚》：'若颠木之有由櫱。'",
     "'若颠木之有由櫱。'",
     "櫱与萌芽同义，训始"),
    ("櫱", "义证",   "广雅疏证",
     "芽米谓之櫱，灾始生谓之孼，义并与'櫱'同。",
     "芽米谓之櫱，灾始生谓之孼，义并与櫱同。",
     "义训"),

    # 鼃（id=15）
    ("鼃", "书证",   "方言",
     "《方言》：'鼃、律，始也。'",
     "'鼃、律，始也。'",
     "证「鼃」训始"),

    # 䔞（id=16）
    ("䔞", "书证",   "说文解字",
     "《说文》：'肁，始开也，从户聿。' '聿'亦始也，声与'䔞'近而义同。",
     "'肁，始开也，从户聿。' '聿'亦始也，声与䔞近而义同。",
     "证「䔞」训始，聿声近义同"),
    ("䔞", "义证",   "广雅疏证",
     "凡事之始即为之法，故始谓之方，亦谓之律，法谓之律，亦谓之方矣。",
     "始谓之方，亦谓之律。",
     "义理互训"),

    # 律（id=17）
    ("律", "书证",   "方言",
     "《方言》：'鼃、律，始也。' '律'与'䔞'通。",
     "'鼃、律，始也。' 律与䔞通。",
     "证「律」训始"),

    # 昌（id=18）
    ("昌", "书证",   "楚辞",
     "王逸注《九章》云：'倡，始也。'",
     "王逸注：'倡，始也。'",
     "昌通倡，证「倡」训始"),
    ("昌", "书证",   "周礼",
     "《周官·乐师》'教恺歌，遂倡之'，郑注：'故书\u201c倡\u201d为\u201c昌\u201d。'",
     "'故书「倡」为「昌」。'",
     "昌、倡通假"),

    # 鼻（id=20）
    ("鼻", "书证",   "说文解字",
     "《说文》：'自，始也'，'读若鼻，今俗以始生子为鼻子，是。'",
     "'自，始也，读若鼻。'",
     "鼻通自，证「自」训始"),
    ("鼻", "书证",   "方言",
     "《方言》：'鼻，始也。嘼之初生谓之鼻，人之初生谓之首。'",
     "'鼻，始也。嘼之初生谓之鼻。'",
     "证「鼻」训始"),
    ("鼻", "异文",   "庄子",
     "《庄子·天地篇》'谁其比忧'，'比'，司马彪本作'鼻'，云：'始也。'",
     "'比'，司马彪本作'鼻'，云：'始也。'",
     "异文证义"),
    ("鼻", "书证",   "汉书",
     "《汉书·扬雄传》'或鼻祖于汾隅'，刘德注亦云：'鼻，始也。'",
     "刘德注：'鼻，始也。'",
     "书证「鼻」训始"),

    # 業（id=21）
    ("業", "书证",   "国语",
     "《齐语》：'择其善者而业用之'，韦昭注：'业犹创也。'",
     "韦昭注：'业犹创也。'",
     "業通創，训始"),
    ("業", "书证",   "庄子",
     "《庄子·秋水篇》：'将忘子之故，失子之业。'",
     "'将忘子之故，失子之业。'",
     "補正：业谓本业、始基"),
    ("業", "书证",   "史记",
     "《史记·太史公自序》：'项梁业之，子羽接之。'",
     "'项梁业之，子羽接之。'",
     "業训始、创业"),
]


# ─── 辅助函数 ───────────────────────────────────────────────────────────────

def parse_aliases(aliases_raw) -> list:
    """解析 aliases，可能是 list 或字符串"""
    if isinstance(aliases_raw, list):
        return aliases_raw
    if isinstance(aliases_raw, str):
        if not aliases_raw.strip():
            return []
        try:
            return json.loads(aliases_raw)
        except Exception:
            return []
    return []


def format_row(row: dict) -> str:
    """格式化单行输出"""
    parts = []
    for k, v in row.items():
        if v is None:
            continue
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:58] + "…"
        parts.append(f"  {k}={sv}")
    return "\n".join(parts)


# ─── 录入主函数 ────────────────────────────────────────────────────────────

def import_all(dry_run: bool = False):
    """完整录入流程"""
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    if dry_run:
        print("=" * 60)
        print("DRY RUN — 仅打印 SQL，不写入数据库")
        print("=" * 60)

    # ── 1. 重建数据库 ─────────────────────────────────────────────────
    if not dry_run:
        print("\n[1/5] 重建数据库…")
        db2.reset()
    else:
        print("\n[1/5] (dry) 重建数据库 → db2.reset()")

    # ── 2. 录入 works ────────────────────────────────────────────────
    print("\n[2/5] 录入著作表（15 部典籍）…")
    for row in WORKS:
        wid, title, author, work_type, dynasty, time_note, notes = row
        if dry_run:
            print(f"  works: id={wid} {title} ({dynasty}) {author}")
        else:
            got = db2.upsert_work(title, author, work_type, dynasty, time_note, notes)
            assert got == wid, f"期望 id={wid}，实际={got}"
            print(f"  [OK] [{wid}] {title}")

    # ── 3. 录入 passages ───────────────────────────────────────────────
    print("\n[3/5] 录入文本片段表…")
    if not dry_run:
        passage_id = db2.insert_passage(
            work_id      = 1,
            juan         = "第一上",
            chapter      = "释诂",
            location_note = "始也条",
            raw_text      = ERWANG_FULL_TEXT,
            normalized_text = ERWANG_FULL_TEXT,
            passage_type  = "二王论述",
        )
        print(f"  [OK] passage_id={passage_id} 《广雅疏证·释诂「始也」条》")
    else:
        print(f"  passages: work_id=1, juan=第一上, chapter=释诂, location=始也条")

    # ── 4. 录入 terms ─────────────────────────────────────────────────
    print("\n[4/5] 录入词条表（21 个词条）…")
    term_id_map = {}  # term_char → term_id

    for i, (term, term_type, category, aliases, core_meaning, notes) in enumerate(TERMS_DEF):
        if dry_run:
            print(f"  terms: {term} ({term_type}) core={core_meaning[:30]}…")
        else:
            tid = db2.insert_term(
                term          = term,
                term_type     = term_type,
                category      = category,
                aliases       = aliases,
                notes         = notes,
                core_meaning  = core_meaning,
            )
            term_id_map[term] = tid
            print(f"  [OK] [{tid}] {term} | {category} | {core_meaning[:40]}…")

    # ── 5. 录入 case ──────────────────────────────────────────────────
    print("\n[5/5] 录入考据案例表 + 证据表（22 条）…")
    all_term_ids = list(term_id_map.values())

    if not dry_run:
        case_id = db2.insert_case(
            title            = CASE_DEF["title"],
            section_title    = CASE_DEF["section_title"],
            volume_title     = CASE_DEF["volume_title"],
            term_ids         = all_term_ids,
            problem          = CASE_DEF["problem"],
            method           = CASE_DEF["method"],
            process_text     = CASE_DEF["process_text"],
            conclusion       = CASE_DEF["conclusion"],
            certainty        = CASE_DEF["certainty"],
            status           = CASE_DEF["status"],
            erwang_passage_id = passage_id,
        )
        print(f"  [OK] case_id={case_id} 《{CASE_DEF['title']}》")

        # ── 5b. 录入 22 条 evidences ────────────────────────────────
        ev_count = 0
        for (term_char, ev_type, work_title, quote_text, core_snippet, note) in EVIDENCES_DEF:
            tid = term_id_map.get(term_char)
            if tid is None:
                print(f"  ✗ 警告：未找到 term '{term_char}'，跳过证据")
                continue

            work_id = db2.get_work_id(work_title)
            if work_id is None:
                print(f"  ✗ 警告：未找到 work '{work_title}'，跳过证据")
                continue

            eid = db2.insert_evidence(
                case_id         = case_id,
                term_id         = tid,
                evidence_type   = ev_type,
                work_id         = work_id,
                quote_text      = quote_text,
                core_snippet    = core_snippet,
                note            = note,
            )
            ev_count += 1

        print(f"  [OK] 录入 {ev_count} 条证据")

        # ── 5c. 回写 term.case_ids ──────────────────────────────────
        for term_char, tid in term_id_map.items():
            db2.update_term_case_ids(tid, [case_id])

        print("  [OK] term.case_ids 回写完成")

        # ── 统计 ───────────────────────────────────────────────────
        st = db2.stats()
        print(f"\n{'='*50}")
        print(f"  数据库录入完成！")
        print(f"  著作   {st['work_count']:>3}  部")
        print(f"  片段   {st['passage_count']:>3}  条")
        print(f"  词条   {st['term_count']:>3}  个")
        print(f"  案例   {st['case_count']:>3}  条")
        print(f"  证据   {st['evidence_count']:>3}  条")
        print(f"{'='*50}")
        return st
    else:
        print(f"  cases: title={CASE_DEF['title']}, term_ids={all_term_ids}")
        print(f"  evidences: 共 {len(EVIDENCES_DEF)} 条（dry run 跳过）")
        return None


# ─── 入口 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="广雅疏证「始也」条数据录入")
    parser.add_argument("--dry-run", action="store_true", help="仅打印，不写入")
    parser.add_argument("--reset",   action="store_true", help="重建数据库后录入（默认）")
    args = parser.parse_args()

    # --reset 或无参数 → 完整录入
    import_all(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

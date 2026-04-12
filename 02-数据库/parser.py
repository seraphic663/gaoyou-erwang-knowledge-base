"""
parser.py — 《广雅疏证》source.txt 清洗拆分脚本

功能：
  - 读取 source.txt，将其中的「X、X、X，[义]也。」训诂条目
    拆解为 data_importer.py 所需的 TERMS_DEF + EVIDENCES_DEF 格式代码
  - 按词头顺序，将释义段落中的证据归属到每个字
  - 记录所有无法解析而被略过的文本（SKIP_LOG）
  - 生成完整 Works 表引用（自动从引文中提取书名）

用法：
  python parser.py                 # 输出到控制台
  python parser.py --output parsed_data.py   # 输出到文件
  python parser.py --verbose       # 显示详细处理过程
  python parser.py --limit 5      # 仅处理前 N 条（测试用）
"""

import sys
import re
import json
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# ─── 配置 ────────────────────────────────────────────────────────────────────

SOURCE_FILE = Path(__file__).parent / "source.txt"

# ─── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class ParsedTerm:
    term: str
    term_type: str
    category: str
    gloss: str
    aliases: list
    core_meaning: str
    explanation: str
    line_no: int
    evidence_type: str
    work_title: str
    quote_text: str
    core_snippet: str
    note: str
    raw_text: str
    is_skipped: bool


@dataclass
class SkippedBlock:
    line_no: int
    content: str
    reason: str
    severity: str


# ─── 词头行解析 ─────────────────────────────────────────────────────────────

def is_entry_head_line(line: str) -> bool:
    """
    判断一行是否为训诂条目词头行（格式：X、X、X…，[义]也。）

    区分词头行与普通段落：
      - 词头行：词头字以顿号/逗号分隔，各段很短（≤20字），结尾「X也。」
      - 普通段落：包含长解释语段，段内含句号、者、之等结构
    """
    s = line.strip()
    if not s:
        return False

    # 必须以汉字开头
    if not ('\u4e00' <= s[0] <= '\u9fff'):
        return False

    # 必须以「X也」或「X也。」结尾
    if not re.search(r'[\u4e00-\u9fff]也[。]?$', s):
        return False

    # ── 段长度过滤：词头行每个词头段极短（≤20字）
    # 去掉结尾「，X也。」部分
    before = re.sub(r'[,，][\u4e00-\u9fff]+也[。]?$', '', s)
    # 去掉 [补字] 标注
    before = re.sub(r'\[[^\]]+\]', '', before)
    # 按顿号/逗号/空格分割
    segments = re.split(r'[,，、\s]+', before)
    segments = [seg for seg in segments if seg]

    # 如果某段特别长（>22字），说明不是词头行
    for seg in segments:
        if len(seg) > 22:
            return False

    # ── 各段必须是纯汉字（词头），不允许夹杂句子结构词
    # 词头段特征：只含汉字，不含以下结构词
    for seg in segments:
        # 跳过纯反切注音
        if re.match(r'^[a-zA-Z\u4e00-\u9fff]+$', seg) and re.search(r'[反音]', seg):
            continue
        # 段中含句末虚词（「者」「之」「云」「也」「焉」「乎」「耶」）→ 普通段落
        if re.search(r'[者之云也焉乎耶]', seg) and len(seg) > 4:
            return False
        # 含空格 → 说明是从段落中误提取
        if ' ' in seg:
            return False

    # ── 至少 2 个词头字（顿号分隔）
    head_chars = extract_head_chars(s)
    if len(head_chars) < 2:
        return False

    return True


def extract_head_chars(head_line: str) -> list[str]:
    """
    从词头行提取词头字序列。
    过滤掉反切注音（如「戶瓜反」）和读音标注。

    例：`古、昔、先、創、方、作、造、朔、萌、芽、本、根、櫱、鼃、戶瓜反 䔞、律 昌、孟、鼻、業，始也。`
      → ["古","昔","先","創","方","作","造","朔","萌","芽","本","根","櫱","鼃","律","昌","孟","鼻","業"]
    """
    # 去掉结尾的「，X也。」或「X也。」
    text = re.sub(r'[,，][\u4e00-\u9fff]+也[。]?$', '', head_line)
    # 去掉 [补字] 这种标注
    text = re.sub(r'\[[^\]]+\]', '', text)

    # 按顿号/空格/逗号分割
    raw_segments = re.split(r'[,，、\s]+', text)
    segments = [s.strip() for s in raw_segments if s.strip()]

    result: list[str] = []
    for seg in segments:
        # 跳过含语义标记「X也」（此为释义标记，非词头字）
        if re.search(r'[\u4e00-\u9fff]也$', seg):
            continue
        # 跳过含句末虚词的段（非纯词头）
        if re.search(r'[者也之乎焉耶]', seg) and len(seg) > 2:
            continue
        # 跳过无汉字的段
        if not re.search(r'[\u4e00-\u9fff]', seg):
            continue
        # 跳过含标点的混合段
        if re.search(r'[，。；：""''（）【】『』·]', seg):
            continue
        # 只取纯汉字字符
        chars = re.findall(r'[\u4e00-\u9fff]', seg)
        result.extend(chars)

    return result


def extract_gloss(head_line: str) -> str:
    """
    从词头行提取训诂义项（如「始也」→「始」）。

    规则：取行末尾的「X也」模式（忽略行中间的「X也」片段）。
    例：`乾、官、元、首，主上也。` → 「主」
    """
    # 贪心匹配 .* 后回溯取末尾的「X也」——回溯确保 X 是单独的汉字
    # 「素丹好也」→「好」 「，始也」→「始」 「，大也」→「大」
    m = re.search(r'.([\u4e00-\u9fff])也[。]?$', head_line)
    return m.group(1) if m else ""


# ─── 释义段落归属 ───────────────────────────────────────────────────────────

def split_body_by_char(
    head_chars: list[str],
    body_lines: list[tuple[int, str]]
) -> dict[str, str]:
    """
    将释义段落按词头字分配到每个字。

    精确归属策略（句子级）：
    - 每行按「。」或「；」拆分为独立句子
    - 含「X者」的句子 → 仅归属给 X（X 必须是词头字）
    - 不含「X者」的句子 → 归属给上一个有标记句子的归属字
    - 段落第一句无标记 → 仅归属给首字（首字专用句）
    """
    sc = sorted(head_chars, key=len, reverse=True)
    hc_first = sc[0] if sc else ""

    full_text = "\n".join(text for _, text in body_lines)
    char_sents: dict[str, list[str]] = {ch: [] for ch in head_chars}

    current_chars: list[str] = []

    for line_text in full_text.splitlines():
        stripped = line_text.strip()
        if not stripped or stripped.startswith("【"):
            continue

        raw_sents = re.split(r"[。；]", stripped)
        sents = [s.strip() for s in raw_sents if s.strip()]

        for sent in sents:
            marker_hit = None
            for ch in sc:
                m = re.match(rf"^([{re.escape(ch)}]+)者", sent)
                if m:
                    matched_str = m.group(1)
                    marked_chars: list[str] = []
                    tmp = matched_str
                    while tmp:
                        found_ch = None
                        for c2 in sc:
                            if tmp.startswith(c2):
                                found_ch = c2
                                break
                        if found_ch:
                            marked_chars.append(found_ch)
                            tmp = tmp[len(found_ch):]
                            if tmp.startswith("、"):
                                tmp = tmp[1:]
                        else:
                            break
                    if marked_chars:
                        marker_hit = marked_chars
                        current_chars = marked_chars
                        break

            if marker_hit is not None:
                for c in current_chars:
                    char_sents[c].append(sent)
            else:
                if not current_chars and hc_first:
                    current_chars = [hc_first]
                if current_chars:
                    for c in current_chars:
                        char_sents[c].append(sent)

    result: dict[str, str] = {}
    for ch in head_chars:
        sents = char_sents[ch]
        result[ch] = "\n".join(sents) if sents else ""

    items = list(result.items())
    for idx in range(len(items)):
        ch, text = items[idx]
        if not text.strip():
            for j in range(idx - 1, -1, -1):
                if items[j][1].strip():
                    result[ch] = items[j][1]
                    break
            if not result[ch].strip():
                for j in range(idx + 1, len(items)):
                    if items[j][1].strip():
                        result[ch] = items[j][1]
                        break

    return result


# ─── 证据提取 ───────────────────────────────────────────────────────────────

def infer_category(gloss: str, term: str, explanation: str) -> str:
    """推断词条分类"""
    if re.search(rf"'{re.escape(term)}'之言", explanation):
        return "声训·通假字"
    if re.search(r"讀[爲若]", explanation):
        return "音训·通假字"
    if "方言" in explanation:
        return "方言俗语"
    return "同义实词"


def extract_evidence_type(explanation: str) -> str:
    if re.search(rf"'[^']+'之言", explanation):
        return "声训"
    if re.search(r"讀[爲若]", explanation):
        return "音训"
    if re.search(r"相對成文|對文", explanation):
        return "语法证据"
    if re.search(r"通作|相通|亦通|聲近義同|通用", explanation):
        return "异文"
    if re.search(r"同義|義並|義與", explanation):
        return "义证"
    if re.search(r"《", explanation):
        return "书证"
    return "义证"


def extract_work_title(explanation: str) -> str:
    books = re.findall(r'《([^》·]+(?:[·][^》]+)?)》', explanation)
    return books[0] if books else "广雅疏证"


def extract_core_snippet(explanation: str, term: str, gloss: str) -> str:
    sentences = re.split(r'[。；]', explanation)
    for s in sentences:
        s = s.strip()
        if len(s) >= 4 and ('也' in s or term in s or gloss in s):
            return s[:80] + ("…" if len(s) > 80 else "")
    if sentences:
        first = sentences[0].strip()
        return first[:80] + ("…" if len(first) > 80 else "")
    return explanation[:80]


# ─── Works 表 ────────────────────────────────────────────────────────────────

CANONICAL_WORK_NAMES = {
    "广雅疏证", "广雅", "毛诗", "尚书", "礼记", "方言",
    "说文解字", "孟子", "吕氏春秋", "周礼", "庄子", "国语",
    "史记", "汉书", "楚辞", "老子", "墨子", "尔雅",
    "春秋", "左传", "公羊传", "谷梁传", "大学", "中庸",
    "白虎通义", "管子", "晏子春秋", "淮南子", "逸周书",
    "盐铁论", "后汉书", "文选", "玉篇", "广韵",
    "风俗通义", "艺文类聚", "太玄", "韩诗", "春秋繁露",
    "说苑", "考工记", "仪礼", "韩非子", "贾子", "新序",
    "战国策", "法言", "论衡", "三苍",
}


# ─── 主解析器 ───────────────────────────────────────────────────────────────

def parse_source_file(
    limit: int = 0,
    verbose: bool = False,
) -> tuple[list[ParsedTerm], list[SkippedBlock]]:

    lines = SOURCE_FILE.read_text(encoding="utf-8").splitlines()

    parsed_terms: list[ParsedTerm] = []
    skipped_blocks: list[SkippedBlock] = []

    current_head: Optional[dict] = None
    body_lines: list[tuple[int, str]] = []
    entry_count = 0

    def finalize_head(head: dict) -> None:
        nonlocal parsed_terms, entry_count, skipped_blocks
        head_chars = head["head_chars"]
        gloss = head["gloss"]
        body = head["body_lines"]

        if not head_chars:
            return

        char_exp = split_body_by_char(head_chars, body)
        matched_lines: set[int] = set()  # 行号集合

        for ch in head_chars:
            exp_text = char_exp.get(ch, "")
            ev_type = extract_evidence_type(exp_text)
            work = extract_work_title(exp_text)
            core = extract_core_snippet(exp_text, ch, gloss)
            category = infer_category(gloss, ch, exp_text)

            # 标记该字的释义行已被使用
            for ln, lt in body:
                if ch in lt:
                    matched_lines.add(ln)

            pt = ParsedTerm(
                term           = ch,
                term_type      = "词",
                category       = category,
                gloss          = gloss,
                aliases        = [],
                core_meaning   = (f"「{ch}」训「{gloss}」，"
                                  f"{exp_text[:80]}{'...' if len(exp_text)>80 else ''}").strip(),
                explanation    = exp_text,
                line_no        = head["line_no"],
                evidence_type  = ev_type,
                work_title     = work,
                quote_text     = exp_text[:200],
                core_snippet   = core,
                note           = "",
                raw_text       = exp_text,
                is_skipped     = bool(not exp_text.strip()),
            )
            parsed_terms.append(pt)

            # 记录空归属字条
            if not exp_text.strip():
                skipped_blocks.append(SkippedBlock(
                    line_no   = head["line_no"],
                    content   = f"[char={ch}] gloss={gloss} attr=EMPTY",
                    reason    = f"字「{ch}」在释义段落中未匹配到归属文本",
                    severity  = "warn",
                ))

        # 记录未被任何字归属的行（复杂段落、補正等）
        for ln, lt in body:
            lt_stripped = lt.strip()
            if not lt_stripped or lt_stripped.startswith("【"):
                continue
            # 简单检查：这一行是否含任何词头字
            has_head_char = any(c in lt for c in head_chars)
            if not has_head_char and len(lt_stripped) > 10:
                skipped_blocks.append(SkippedBlock(
                    line_no   = ln,
                    content   = lt_stripped[:200],
                    reason    = f"段落行（无词头字归属）「{gloss}也」词条",
                    severity  = "info",
                ))

        entry_count += 1
    if verbose:
        print(f"  [OK] gloss={gloss} -> {len(head_chars)} chars")

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # 跳过前言、卷首等非训诂行
        if _is_skip_zone(line):
            i += 1
            continue

        # ── 检测词头行 ──────────────────────────────────────────────────
        if is_entry_head_line(line):
            # 结束上一个词条
            if current_head is not None:
                finalize_head(current_head)
                if limit > 0 and entry_count >= limit:
                    break

            head_chars = extract_head_chars(line)
            gloss = extract_gloss(line)

            current_head = {
                "line_no":    i + 1,
                "gloss":      gloss,
                "head_chars": head_chars,
                "head_raw":   line,
                "body_lines": [],
            }
            if verbose:
                print(f"  [HEAD] line {i+1}: gloss={gloss} chars={head_chars}")
            i += 1
            continue

        # ── 累积释义段落 ──────────────────────────────────────────────
        if current_head is not None:
            stripped = line.strip()
            if stripped:
                # 【補正】/【墨簽】整体作为 body 累积，由 finalize 处理
                current_head["body_lines"].append((i + 1, stripped))

                # 检测词条结束：遇到下一条词头（不同词头行）
                if (is_entry_head_line(stripped)
                        and stripped != current_head["head_raw"]):
                    finalize_head(current_head)
                    current_head = None
                    if limit > 0 and entry_count >= limit:
                        break

        i += 1

    # 处理最后一条词条
    if current_head is not None:
        finalize_head(current_head)

    if verbose:
        print(f"  Done: {entry_count} entries, {len(parsed_terms)} char-terms")

    return parsed_terms, skipped_blocks


def _is_skip_zone(line: str) -> bool:
    """判断是否属于需要跳过的非训诂区域"""
    s = line.strip()
    if not s:
        return False
    if not re.search(r'[\u4e00-\u9fff]', s):
        return True
    skip_prefixes = (
        "广雅疏证序", "段玉裁序", "王念孙自序", "上广雅表",
        "廣雅疏證序", "博士臣揖言",
        "廣雅疏證卷", "广雅疏证卷",
        "釋詁", "釋言", "釋訓", "釋親", "釋樂", "釋水",
        "卷第",
    )
    for p in skip_prefixes:
        if s.startswith(p):
            return True
    return False


# ─── 输出格式化 ─────────────────────────────────────────────────────────────

def format_terms_def(parsed: list[ParsedTerm]) -> str:
    lines = [
        "",
        "# ═══════════════════════════════════════════════════════════════════════",
        "#  TERMS_DEF — 自动生成 by parser.py",
        "# ═══════════════════════════════════════════════════════════════════════",
        "",
        "TERMS_DEF = [",
    ]
    seen: set[str] = set()
    for pt in parsed:
        if pt.term in seen:
            continue
        seen.add(pt.term)
        a = json.dumps(pt.aliases, ensure_ascii=False)
        lines.append(f"    # 行 {pt.line_no}  「{pt.gloss}也」")
        lines.append(f"    ({json.dumps(pt.term, ensure_ascii=False)}, "
                     f"{json.dumps(pt.term_type, ensure_ascii=False)}, "
                     f"{json.dumps(pt.category, ensure_ascii=False)}, "
                     f"{a}, "
                     f"{json.dumps(pt.core_meaning[:100], ensure_ascii=False)}, "
                     f"{json.dumps(pt.note, ensure_ascii=False)}),")
    lines.append("]")
    return "\n".join(lines)


def format_evidences_def(parsed: list[ParsedTerm]) -> str:
    lines = [
        "",
        "# ═══════════════════════════════════════════════════════════════════════",
        "#  EVIDENCES_DEF — 自动生成 by parser.py",
        "#  (term_char, evidence_type, work_title, quote_text, core_snippet, note)",
        "# ═══════════════════════════════════════════════════════════════════════",
        "",
        "EVIDENCES_DEF = [",
    ]
    for pt in parsed:
        if not pt.explanation.strip():
            continue
        lines.append(f"    # ── {pt.term}（行 {pt.line_no}）  「{pt.gloss}也」")
        lines.append(f"    ({json.dumps(pt.term, ensure_ascii=False)}, "
                     f"{json.dumps(pt.evidence_type, ensure_ascii=False)}, "
                     f"{json.dumps(pt.work_title, ensure_ascii=False)}, "
                     f"{json.dumps(pt.quote_text[:150], ensure_ascii=False)}, "
                     f"{json.dumps(pt.core_snippet[:80], ensure_ascii=False)}, "
                     f"{json.dumps(pt.note, ensure_ascii=False)}, "
                     f"{pt.line_no}),")
    lines.append("]")
    return "\n".join(lines)


def format_works_def() -> str:
    lines = [
        "",
        "# ═══════════════════════════════════════════════════════════════════════",
        "#  WORKS — 自动生成 by parser.py",
        "# ═══════════════════════════════════════════════════════════════════════",
        "",
        "WORKS = [",
    ]
    for i, wname in enumerate(sorted(CANONICAL_WORK_NAMES), 1):
        lines.append(f"    # {i:2d}  {wname}")
        lines.append(f"    ({i}, {json.dumps(wname, ensure_ascii=False)}, "
                     f'"{wname}", "原始经典", "", "", ""),')
    lines.append("]")
    return "\n".join(lines)


def format_skip_log(skipped: list[SkippedBlock]) -> str:
    lines = [
        "",
        "# ═══════════════════════════════════════════════════════════════════════",
        "#  SKIP_LOG — 被略过的文本（无法自动解析）",
        "# ═══════════════════════════════════════════════════════════════════════",
        "",
        "SKIP_LOG = [",
    ]
    if not skipped:
        lines.append("    # 无被略过内容")
    for s in skipped:
        lines.append(f"    # 行 {s.line_no} [{s.severity}] {s.reason}")
        lines.append(f"    {json.dumps(s.content[:100], ensure_ascii=False)},")
    lines.append("]")
    return "\n".join(lines)


# ─── 入口 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="《广雅疏证》source.txt 清洗拆分工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "\n用法示例：\n"
            "  python parser.py                     # 打印全部\n"
            "  python parser.py -v                   # 详细输出\n"
            "  python parser.py -n 5                # 仅前 5 条（测试）\n"
            "  python parser.py -o parsed_data.py   # 输出到文件\n"
        ),
    )
    parser.add_argument("-o", "--output", metavar="FILE", help="输出到文件")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细过程")
    parser.add_argument("-n", "--limit", metavar="N", type=int, default=0,
                        help="最多处理 N 条词条（测试用）")
    args = parser.parse_args()

    print("=" * 60)
    print("[parser] source.txt 清洗拆分")
    print("=" * 60)
    print(f"源文件：{SOURCE_FILE}")
    print(f"模式：{'verbose' if args.verbose else 'quiet'}"
          f"{' | limit=' + str(args.limit) if args.limit else ''}")
    print()

    parsed, skipped = parse_source_file(limit=args.limit, verbose=args.verbose)

    if not parsed:
        print("[警告] 未解析到任何词条，请检查 source.txt 文件路径和格式")
        return

    terms_out   = format_terms_def(parsed)
    evids_out   = format_evidences_def(parsed)
    works_out   = format_works_def()
    skip_out    = format_skip_log(skipped)

    full = (
        "# -*- coding: utf-8 -*-\n"
        "# -------------------------------------------------------------\n"
        "#  parsed_data.py — auto-generated by parser.py\n"
        "#  source: source.txt\n"
        "# -------------------------------------------------------------\n\n"
        + works_out + "\n\n"
        + terms_out + "\n\n"
        + evids_out + "\n\n"
        + skip_out + "\n"
    )

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    if args.output:
        Path(args.output).write_text(full, encoding="utf-8")
        print(f"\n[Saved] -> {args.output}")
        print(f"  WORKS         {len(CANONICAL_WORK_NAMES)} entries")
        print(f"  TERMS_DEF     {len(set(p.term for p in parsed))} unique chars")
        print(f"  EVIDENCES_DEF {len([p for p in parsed if p.explanation.strip()])} entries")
        print(f"  SKIP_LOG      {len(skipped)} entries")
    else:
        print(full)

    print("\n" + "=" * 40)
    print("  [Summary]")
    print("=" * 40)
    gloss_count: dict[str, int] = {}
    for pt in parsed:
        g = pt.gloss
        gloss_count[g] = gloss_count.get(g, 0) + 1
    print(f"  Entry heads   {len(set(pt.line_no for pt in parsed))}")
    print(f"  Char-terms   {len(parsed)}")
    print(f"  Unique chars {len(set(pt.term for pt in parsed))}")
    print(f"  Skipped      {len(skipped)}")
    print()
    print("  Gloss distribution (top 10):")
    for g, cnt in sorted(gloss_count.items(), key=lambda x: -x[1])[:10]:
        print(f"    {g}也  x{cnt}")


if __name__ == "__main__":
    main()

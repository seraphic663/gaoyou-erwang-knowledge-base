"""
db2.py — 古汉语考据数据库 · A方案五表结构

表结构：
  works        著作表（source works / primary sources）
  passages     文本片段表（erwang commentary passages）
  terms        词条表（character / word entries: 20 synonym group members）
  cases        考据案例表（one master case per annotation section）
  evidences    证据表（individual citations backing the case）

Design principles:
  - 每个字（term）独立一行 → 搜索无重复
  - 证据（evidence）按"字"维度聚合 → 每次检索聚焦单字
  - 核心句（core_snippet）直接存 DB → 无需 LLM 实时提炼
  - 证据类型分类：书证 / 声训 / 义证 / 语法证据 / 异文
"""

import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).parent / "data2" / "dictionary.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_connection: Optional[sqlite3.Connection] = None


# ─── 连接管理 ──────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _init_schema(_connection)
    return _connection


def close():
    global _connection
    if _connection:
        _connection.close()
        _connection = None


def reset():
    """删除数据库文件并重建空表（处理 Windows 文件锁）"""
    close()
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except PermissionError:
            import time
            for _ in range(3):
                time.sleep(0.3)
                try:
                    DB_PATH.unlink()
                    break
                except PermissionError:
                    pass
    get_conn()


# ─── Schema ────────────────────────────────────────────────────────────────

_SCHEMA = """
-- 著作表：所有被引用的典籍
CREATE TABLE IF NOT EXISTS works (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL UNIQUE,
    author     TEXT,
    work_type  TEXT CHECK(work_type IN ('二王著作','原始经典')),
    dynasty    TEXT,
    time_note  TEXT,
    notes      TEXT
);

-- 文本片段表：二王论述段落
CREATE TABLE IF NOT EXISTS passages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id          INTEGER REFERENCES works(id),
    juan             TEXT,
    chapter          TEXT,
    location_note    TEXT,
    raw_text         TEXT NOT NULL,
    normalized_text  TEXT,
    passage_type     TEXT CHECK(passage_type IN ('二王论述','原始经典'))
);

-- 词条表：每个字/词独立一行，无重复
CREATE TABLE IF NOT EXISTS terms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    term        TEXT NOT NULL,
    term_type   TEXT CHECK(term_type IN ('术语','词','字')),
    category    TEXT,
    aliases     TEXT,
    notes       TEXT,
    -- 核心训释（一两句话的精准提炼）
    core_meaning TEXT,
    -- 所属案例（JSON 数组，避免重复关联表）
    case_ids    TEXT,
    UNIQUE(term)
);

-- 考据案例表：整条"始也"考证为一个 case
CREATE TABLE IF NOT EXISTS cases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    section_title       TEXT,
    volume_title        TEXT,
    term_ids            TEXT,
    erwang_passage_id   INTEGER REFERENCES passages(id),
    target_passage_id   INTEGER REFERENCES passages(id),
    problem             TEXT,
    method              TEXT,
    process_text        TEXT,
    conclusion          TEXT,
    certainty           TEXT CHECK(certainty IN ('确定','可疑','待核')),
    status              TEXT CHECK(status IN ('草稿','已校对','已审核'))
);

-- 证据表：每个证据关联到特定字（term），独立一行
CREATE TABLE IF NOT EXISTS evidences (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id             INTEGER REFERENCES cases(id),
    -- 证据归哪个字（字 → 证据，一对多）
    term_id             INTEGER REFERENCES terms(id),
    source_passage_id   INTEGER REFERENCES passages(id),
    work_id             INTEGER REFERENCES works(id),
    evidence_type       TEXT CHECK(evidence_type IN ('书证','声训','义证','形证','语法证据','异文')),
    quote_text          TEXT,
    -- 核心引用句：对该字而言最关键的一两句（手工提炼或后处理填充）
    core_snippet        TEXT,
    note                TEXT
);

-- FTS 全文索引（搜索 raw_text / quote_text / core_snippet）
CREATE VIRTUAL TABLE IF NOT EXISTS terms_fts USING fts5(
    term, category, aliases, notes, core_meaning
);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    raw_text, normalized_text
);
CREATE VIRTUAL TABLE IF NOT EXISTS evidences_fts USING fts5(
    quote_text, core_snippet, note
);
"""


def _init_schema(conn: sqlite3.Connection):
    for stmt in _SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception as e:
                if "already exists" not in str(e):
                    raise
    conn.commit()


# ─── works ─────────────────────────────────────────────────────────────────

def upsert_work(title: str, author: str = None, work_type: str = None,
                dynasty: str = None, time_note: str = None, notes: str = None) -> int:
    conn = get_conn()
    row = conn.execute("SELECT id FROM works WHERE title=?", (title,)).fetchone()
    if row:
        return row["id"]
    conn.execute(
        "INSERT INTO works(title,author,work_type,dynasty,time_note,notes) "
        "VALUES(?,?,?,?,?,?)",
        (title, author, work_type, dynasty, time_note, notes)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def bulk_upsert_works(rows: list[tuple]) -> dict[str, int]:
    """
    批量插入 works，返回 {title: id} 映射。
    rows 格式：[(title, author, work_type, dynasty, time_note, notes), ...]
    """
    conn = get_conn()
    wmap: dict[str, int] = {}
    for (title, author, work_type, dynasty, time_note, notes) in rows:
        if not title:
            continue
        row = conn.execute("SELECT id FROM works WHERE title=?", (title,)).fetchone()
        if row:
            wmap[title] = row["id"]
        else:
            conn.execute(
                "INSERT INTO works(title,author,work_type,dynasty,time_note,notes) "
                "VALUES(?,?,?,?,?,?)",
                (title, author, work_type, dynasty, time_note, notes)
            )
            wid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            wmap[title] = wid
    conn.commit()
    return wmap


def get_work_id(title: str) -> Optional[int]:
    row = get_conn().execute("SELECT id FROM works WHERE title=?", (title,)).fetchone()
    return row["id"] if row else None


def get_all_works() -> List[Dict]:
    rows = get_conn().execute("SELECT * FROM works ORDER BY id").fetchall()
    return [dict(r) for r in rows]


# ─── passages ──────────────────────────────────────────────────────────────

def insert_passage(work_id: int, raw_text: str, passage_type: str,
                   juan: str = None, chapter: str = None,
                   location_note: str = None, normalized_text: str = None) -> int:
    conn = get_conn()
    conn.execute(
        """INSERT INTO passages
           (work_id,juan,chapter,location_note,raw_text,normalized_text,passage_type)
           VALUES(?,?,?,?,?,?,?)""",
        (work_id, juan, chapter, location_note, raw_text, normalized_text, passage_type)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_passage_by_id(passage_id: int) -> Optional[Dict]:
    row = get_conn().execute("SELECT * FROM passages WHERE id=?", (passage_id,)).fetchone()
    return dict(row) if row else None


# ─── terms ─────────────────────────────────────────────────────────────────

def insert_term(term: str, term_type: str = "字", category: str = None,
                 aliases: List[str] = None, notes: str = None,
                 core_meaning: str = None, case_ids: List[int] = None) -> int:
    conn = get_conn()
    row = conn.execute("SELECT id FROM terms WHERE term=?", (term,)).fetchone()
    if row:
        return row["id"]
    aliases_json = json.dumps(aliases, ensure_ascii=False) if aliases else None
    case_ids_json = json.dumps(case_ids or [], ensure_ascii=False) if case_ids else None
    conn.execute(
        "INSERT INTO terms(term,term_type,category,aliases,notes,core_meaning,case_ids) "
        "VALUES(?,?,?,?,?,?,?)",
        (term, term_type, category, aliases_json, notes, core_meaning, case_ids_json)
    )
    conn.commit()
    term_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    # 同步 FTS
    conn.execute(
        "INSERT INTO terms_fts(rowid,term,category,aliases,notes,core_meaning) "
        "VALUES(?,?,?,?,?,?)",
        (term_id, term, category, aliases_json, notes, core_meaning)
    )
    conn.commit()
    return term_id


def update_term_case_ids(term_id: int, case_ids: List[int]):
    """将 case_ids 合并写入 term（用于所有字录入后统一更新关联）"""
    conn = get_conn()
    conn.execute("UPDATE terms SET case_ids=? WHERE id=?",
                 (json.dumps(case_ids, ensure_ascii=False), term_id))
    conn.commit()


def bulk_insert_terms(rows: list) -> dict:
    """
    批量插入 terms（已存在则跳过），返回 {term: id} 映射。
    rows 格式：[(term, term_type, category, aliases_list, notes, core_meaning), ...]
    """
    conn = get_conn()
    tmap: dict = {}
    for (term, term_type, category, aliases, notes, core_meaning) in rows:
        if not term:
            continue
        row = conn.execute("SELECT id FROM terms WHERE term=?", (term,)).fetchone()
        if row:
            tmap[term] = row["id"]
            continue
        als_json = json.dumps(aliases, ensure_ascii=False) if aliases else None
        conn.execute(
            "INSERT INTO terms(term,term_type,category,aliases,notes,core_meaning,case_ids) "
            "VALUES(?,?,?,?,?,?,?)",
            (term, term_type, category, als_json, notes, core_meaning, None)
        )
        tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO terms_fts(rowid,term,category,aliases,notes,core_meaning) "
            "VALUES(?,?,?,?,?,?)",
            (tid, term, category, als_json, notes, core_meaning)
        )
        tmap[term] = tid
    conn.commit()
    return tmap



def search_terms(keyword: str, limit: int = 30) -> List[Dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM terms
           WHERE term=? OR term LIKE ? OR aliases LIKE ?
           ORDER BY id LIMIT ?""",
        (keyword, f"%{keyword}%", f"%{keyword}%", limit)
    ).fetchall()
    return [dict(r) for r in rows]


def get_term_by_id(term_id: int) -> Optional[Dict]:
    row = get_conn().execute("SELECT * FROM terms WHERE id=?", (term_id,)).fetchone()
    return dict(row) if row else None


def get_all_terms() -> List[Dict]:
    rows = get_conn().execute("SELECT * FROM terms ORDER BY id").fetchall()
    return [dict(r) for r in rows]


# ─── cases ─────────────────────────────────────────────────────────────────

def insert_case(title: str, section_title: str = None, volume_title: str = None,
                term_ids: List[int] = None, problem: str = None,
                method: str = None, process_text: str = None,
                conclusion: str = None, certainty: str = "确定",
                status: str = "已校对",
                erwang_passage_id: int = None,
                target_passage_id: int = None) -> int:
    conn = get_conn()
    term_ids_json = json.dumps(term_ids or [], ensure_ascii=False)
    conn.execute(
        """INSERT INTO cases
           (title,section_title,volume_title,term_ids,problem,method,
            process_text,conclusion,certainty,status,
            erwang_passage_id,target_passage_id)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (title, section_title, volume_title, term_ids_json, problem,
         method, process_text, conclusion, certainty, status,
         erwang_passage_id, target_passage_id)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def bulk_insert_cases(rows: list) -> list:
    """
    批量插入 cases，返回 [case_id, ...]。
    rows 格式：[(title, section_title, volume_title, term_ids_list, problem, method, conclusion, certainty, status), ...]
    """
    conn = get_conn()
    ids = []
    for (title, section_title, volume_title, term_ids, problem, method, conclusion, certainty, status) in rows:
        tid_json = json.dumps(term_ids or [], ensure_ascii=False)
        conn.execute(
            """INSERT INTO cases
               (title,section_title,volume_title,term_ids,problem,method,
                process_text,conclusion,certainty,status,
                erwang_passage_id,target_passage_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, section_title, volume_title, tid_json, problem,
             method, None, conclusion, certainty, status, None, None)
        )
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        ids.append(cid)
    conn.commit()
    return ids


def get_case_by_id(case_id: int) -> Optional[Dict]:
    row = get_conn().execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    return dict(row) if row else None


def get_cases_for_term_id(term_id: int) -> List[Dict]:
    """通过解析 JSON term_ids 查找关联案例"""
    conn = get_conn()
    all_cases = conn.execute("SELECT * FROM cases ORDER BY id").fetchall()
    result = []
    for row in all_cases:
        d = dict(row)
        tid_str = d.get("term_ids", "[]")
        try:
            ids = json.loads(tid_str)
        except Exception:
            ids = []
        if term_id in ids:
            result.append(dict(row))
    return result


def get_all_cases() -> List[Dict]:
    rows = get_conn().execute("SELECT * FROM cases ORDER BY id").fetchall()
    return [dict(r) for r in rows]


# ─── evidences ──────────────────────────────────────────────────────────────

def insert_evidence(case_id: int, quote_text: str = None,
                    evidence_type: str = "书证", work_id: int = None,
                    source_passage_id: int = None, term_id: int = None,
                    core_snippet: str = None, note: str = None) -> int:
    conn = get_conn()
    conn.execute(
        """INSERT INTO evidences
           (case_id,quote_text,evidence_type,work_id,source_passage_id,term_id,core_snippet,note)
           VALUES(?,?,?,?,?,?,?,?)""",
        (case_id, quote_text, evidence_type, work_id, source_passage_id,
         term_id, core_snippet, note)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def bulk_insert_evidences(rows: list) -> int:
    """
    批量插入 evidences，返回插入数量。
    rows 格式：[(case_id, term_id, evidence_type, work_id, quote_text, core_snippet, note), ...]
    """
    conn = get_conn()
    n = 0
    for (case_id, term_id, evidence_type, work_id, quote_text, core_snippet, note) in rows:
        try:
            conn.execute(
                """INSERT INTO evidences
                   (case_id,quote_text,evidence_type,work_id,source_passage_id,term_id,core_snippet,note)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (case_id, quote_text, evidence_type, work_id, None, term_id, core_snippet, note)
            )
            n += 1
        except Exception:
            pass
    conn.commit()
    return n


def get_evidences_for_case(case_id: int) -> List[Dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT e.*, w.title AS work_title, t.term AS term_char
           FROM evidences e
           LEFT JOIN works w ON w.id=e.work_id
           LEFT JOIN terms t ON t.id=e.term_id
           WHERE e.case_id=?
           ORDER BY e.term_id, e.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_evidences_for_term(term_id: int) -> List[Dict]:
    """获取指定字的所有证据（证据表已按 term_id 归类）"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT e.*, w.title AS work_title
           FROM evidences e
           LEFT JOIN works w ON w.id=e.work_id
           WHERE e.term_id=?
           ORDER BY e.id""",
        (term_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ─── 统计 ─────────────────────────────────────────────────────────────────

def stats() -> Dict[str, int]:
    conn = get_conn()
    cur = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM works)     AS work_count,
            (SELECT COUNT(*) FROM passages)  AS passage_count,
            (SELECT COUNT(*) FROM terms)    AS term_count,
            (SELECT COUNT(*) FROM cases)     AS case_count,
            (SELECT COUNT(*) FROM evidences) AS evidence_count
    """).fetchone()
    return dict(cur)


# ─── 检索 API ───────────────────────────────────────────────────────────────

def search_full(keyword: str) -> Dict[str, Any]:
    """
    搜索结果聚合格式：
      term          单字词条
      core_meaning  核心训释（一两句话）
      evidences      该字所有证据（按类型分组）
      cases          该字参与的所有案例
    """
    terms = search_terms(keyword, limit=10)
    if not terms:
        return {"term": None, "evidences": [], "cases": []}

    term = terms[0]  # 精确匹配优先
    term_id = term["id"]

    evidences = get_evidences_for_term(term_id)
    cases = get_cases_for_term_id(term_id)

    return {
        "term": term,
        "evidences": evidences,
        "cases": cases,
    }

"""
app.py — 古汉语考据数据库 Web 界面（适配 A 方案新五表）
搭配 db2.py 使用，支持搜索、浏览、统计
"""

from flask import Flask, render_template, request, redirect, url_for, abort
import db2
import json

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


# ─── 主页 ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    st = db2.stats()
    return render_template("index.html", stats=st)


# ─── 搜索 ───────────────────────────────────────────────────────────────────

@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("index"))

    # 使用新的 search_full API（无重复，核心句优先）
    result = db2.search_full(q)
    term = result["term"]
    cases = result["cases"]
    evidences = result["evidences"]

    aliases = []
    if term and term.get("aliases"):
        try:
            aliases = json.loads(term["aliases"])
        except Exception:
            pass

    # 文本片段（按关键词搜索）
    passage_results = db2.search_passages(q)

    return render_template(
        "search.html",
        q=q,
        term=term,
        terms=[term] if term else [],
        aliases=aliases,
        cases=cases,
        passages=passage_results,
        evidences=evidences,
    )


# ─── 词条详情（按 ID）───────────────────────────────────────────────────────

@app.route("/term/<int:term_id>")
def term_detail(term_id: int):
    term = db2.get_term_by_id(term_id)
    if not term:
        return "词条不存在", 404

    cases = db2.get_cases_for_term_id(term_id)
    evidences = db2.get_evidences_for_term(term_id)

    aliases = []
    if term.get("aliases"):
        try:
            aliases = json.loads(term["aliases"])
        except Exception:
            pass

    return render_template(
        "term.html",
        term=term,
        aliases=aliases,
        cases=cases,
        evidences=evidences,
    )


# ─── 考据案例详情 ───────────────────────────────────────────────────────────

@app.route("/case/<int:case_id>")
def case_detail(case_id: int):
    case = db2.get_case_by_id(case_id)
    if not case:
        return "案例不存在", 404

    evidences = db2.get_evidences_for_case(case_id)

    term_ids = []
    if case.get("term_ids"):
        try:
            term_ids = json.loads(case["term_ids"])
        except Exception:
            pass

    return render_template(
        "case.html",
        case=case,
        evidences=evidences,
        term_ids=term_ids,
    )


# ─── 浏览所有词条 ───────────────────────────────────────────────────────────

@app.route("/terms")
def all_terms():
    terms = db2.get_all_terms()
    return render_template("terms.html", terms=terms)


# ─── 浏览所有案例 ───────────────────────────────────────────────────────────

@app.route("/cases")
def all_cases():
    cases = db2.get_all_cases()
    return render_template("cases.html", cases=cases)


# ─── 统计页面 ───────────────────────────────────────────────────────────────

@app.route("/stats")
def stats_page():
    st = db2.stats()
    return render_template("stats.html", stats=st)


if __name__ == "__main__":
    st = db2.stats()
    print(f"\n  古汉语考据数据库")
    print(f"  字 {st['term_count']} | 案例 {st['case_count']} | 证据 {st['evidence_count']}")
    print(f"  http://127.0.0.1:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)

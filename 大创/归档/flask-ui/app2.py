"""
app2.py — 古汉语考据系统 · A方案检索界面

设计原则：
  - 无重复结果：每字词独立一行（UNIQUE term）
  - 核心提炼优先：core_meaning 一两句话直接显示
  - 证据归类清晰：书证 / 声训 / 义证 / 异文 分组展示
  - 界面简洁典雅：古籍风格的暖色调排版

运行：python app2.py → http://127.0.0.1:3001
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, render_template_string, jsonify
import db2

app = Flask(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  模板
# ═══════════════════════════════════════════════════════════════════════════════

TPL = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>古汉语考据系统 · 广雅疏证释诂</title>
<style>
  :root {
    --bg:          #faf8f4;
    --card:        #fffefb;
    --accent:      #7b5c2e;
    --accent-hi:   #a07840;
    --text:        #2e1f0e;
    --muted:       #8a7458;
    --border:      #e8dfc8;
    --tag-bg:      #f3ece0;
    --code-bg:     #f8f3e8;
    --ev-book:     #d4ead4;  --ev-book-txt: #2a5a2a;
    --ev-phono:    #e4d4f0;  --ev-phono-txt:#5a2a7a;
    --ev-sense:    #d8e8f8;  --ev-sense-txt:#2a3a6a;
    --ev-variant:  #f4e8d0;  --ev-variant-txt:#6a4a10;
    --ev-gram:     #e8f0e0;  --ev-gram-txt:  #3a5a2a;
    --ev-other:    #f0ece4;  --ev-other-txt: #5a5040;
    --certainty-y: #d4eed4;  --certainty-n: #f8eed4;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Linux Libertine', 'Noto Serif C', 'Source Han Serif CN',
                 'FangSong', 'STFangsong', Georgia, serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.8;
    min-height: 100vh;
  }

  /* ── 顶栏 ── */
  header {
    background: var(--accent);
    color: #fff8ee;
    padding: 0.9rem 2rem;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 2px 10px rgba(0,0,0,0.18);
  }
  header h1 {
    font-size: 1.05rem;
    font-weight: normal;
    letter-spacing: 0.12em;
  }
  .header-sub {
    font-size: 0.72rem;
    opacity: 0.72;
    font-family: monospace;
  }
  .stats-pill {
    margin-left: auto;
    font-size: 0.7rem;
    font-family: monospace;
    background: rgba(255,255,255,0.12);
    border-radius: 20px;
    padding: 0.2rem 0.8rem;
    opacity: 0.85;
  }

  /* ── 搜索区 ── */
  .search-wrap {
    max-width: 640px;
    margin: 2.2rem auto 0.6rem;
    padding: 0 1.5rem;
  }
  .search-form {
    display: flex;
    gap: 0.5rem;
    background: var(--card);
    border: 2px solid var(--border);
    border-radius: 10px;
    padding: 0.5rem;
    box-shadow: 0 3px 14px rgba(0,0,0,0.06);
  }
  .search-form:focus-within { border-color: var(--accent-hi); }
  .search-input {
    flex: 1;
    border: none;
    outline: none;
    font-size: 1.15rem;
    font-family: inherit;
    background: transparent;
    padding: 0.45rem 0.7rem;
    color: var(--text);
  }
  .search-input::placeholder { color: var(--muted); }
  .search-btn {
    background: var(--accent);
    color: #fff8ee;
    border: none;
    border-radius: 7px;
    padding: 0.5rem 1.5rem;
    font-size: 0.92rem;
    cursor: pointer;
    transition: background 0.2s;
    font-family: inherit;
    letter-spacing: 0.05em;
  }
  .search-btn:hover { background: var(--accent-hi); }

  /* ── 快速入口 ── */
  .quick-row {
    max-width: 640px;
    margin: 0 auto;
    padding: 0 1.5rem;
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
    align-items: center;
  }
  .quick-label { font-size: 0.72rem; color: var(--muted); font-family: monospace; margin-right: 0.2rem; }
  .quick-btn {
    font-size: 0.8rem;
    background: var(--tag-bg);
    border: 1px solid var(--border);
    border-radius: 5px;
    padding: 0.18rem 0.52rem;
    cursor: pointer;
    color: var(--text);
    text-decoration: none;
    font-family: 'Noto Serif C', serif;
    transition: all 0.15s;
  }
  .quick-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* ── 主内容 ── */
  .main { max-width: 760px; margin: 1.5rem auto 3rem; padding: 0 1.5rem; }

  /* ── 无结果 / 提示 ── */
  .empty-state {
    text-align: center;
    padding: 3.5rem 1rem;
    color: var(--muted);
    font-size: 1rem;
  }
  .empty-state .hint { font-size: 0.82rem; margin-top: 0.5rem; font-family: monospace; }

  /* ── 术语概览卡 ── */
  .term-hero {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.6rem 2rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    display: flex;
    gap: 1.5rem;
    align-items: flex-start;
  }
  .term-glyph {
    font-size: 4.2rem;
    color: var(--accent);
    line-height: 1;
    flex-shrink: 0;
    min-width: 3.5rem;
    text-align: center;
    padding-top: 0.1rem;
  }
  .term-info { flex: 1; min-width: 0; }
  .term-core {
    font-size: 1.05rem;
    color: var(--text);
    margin-bottom: 0.5rem;
    line-height: 1.6;
    font-style: italic;
  }
  .term-meta-row { display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }
  .badge {
    display: inline-block;
    font-size: 0.68rem;
    padding: 0.1rem 0.42rem;
    border-radius: 4px;
    font-family: monospace;
    white-space: nowrap;
  }
  .badge-type   { background: var(--tag-bg); color: var(--muted); border: 1px solid var(--border); }
  .badge-cat    { background: var(--tag-bg); color: var(--accent); border: 1px solid var(--border); }
  .badge-certainty { background: var(--certainty-y); color: #2a5a2a; }

  /* ── 案例卡片 ── */
  .case-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.4rem;
    margin-bottom: 0.8rem;
    box-shadow: 0 1px 5px rgba(0,0,0,0.04);
  }
  .case-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; flex-wrap: wrap; }
  .case-label {
    font-size: 0.65rem;
    background: var(--accent);
    color: #fff;
    padding: 0.05rem 0.4rem;
    border-radius: 3px;
    font-family: monospace;
    letter-spacing: 0.04em;
  }
  .case-title { font-size: 0.9rem; color: var(--accent); font-weight: bold; }
  .case-meta { font-size: 0.72rem; color: var(--muted); font-family: monospace; margin-bottom: 0.3rem; }
  .case-conclusion {
    font-size: 0.82rem;
    color: var(--muted);
    border-left: 3px solid var(--border);
    padding-left: 0.6rem;
    margin-top: 0.4rem;
    line-height: 1.6;
  }

  /* ── 证据区 ── */
  .evidence-section { margin-bottom: 1rem; }
  .ev-group-label {
    font-size: 0.7rem;
    color: var(--muted);
    font-family: monospace;
    letter-spacing: 0.06em;
    padding: 0.5rem 0 0.4rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 0.6rem;
  }
  .ev-item {
    display: flex;
    gap: 0.6rem;
    margin-bottom: 0.55rem;
    align-items: flex-start;
  }
  .ev-badge {
    font-size: 0.65rem;
    padding: 0.1rem 0.38rem;
    border-radius: 4px;
    white-space: nowrap;
    flex-shrink: 0;
    margin-top: 0.1rem;
    font-family: monospace;
  }
  .ev-badge.书证     { background: var(--ev-book);     color: var(--ev-book-txt); }
  .ev-badge.声训     { background: var(--ev-phono);     color: var(--ev-phono-txt); }
  .ev-badge.义证     { background: var(--ev-sense);     color: var(--ev-sense-txt); }
  .ev-badge.异文     { background: var(--ev-variant);  color: var(--ev-variant-txt); }
  .ev-badge.语法证据 { background: var(--ev-gram);     color: var(--ev-gram-txt); }
  .ev-badge.其他     { background: var(--ev-other);    color: var(--ev-other-txt); }

  .ev-body { flex: 1; min-width: 0; }
  .ev-core {
    background: var(--code-bg);
    border-left: 3px solid var(--accent);
    border-radius: 0 5px 5px 0;
    padding: 0.28rem 0.65rem;
    font-size: 0.88rem;
    color: var(--text);
    line-height: 1.65;
  }
  .ev-full {
    font-size: 0.78rem;
    color: var(--muted);
    margin-top: 0.18rem;
    line-height: 1.55;
    padding-left: 0.65rem;
  }
  .ev-source {
    font-size: 0.72rem;
    color: var(--accent-hi);
    font-family: monospace;
    margin-top: 0.15rem;
    padding-left: 0.65rem;
  }
  .ev-note { font-size: 0.72rem; color: var(--muted); margin-top: 0.1rem; padding-left: 0.65rem; }

  /* ── 脚注 ── */
  footer {
    text-align: center;
    padding: 1.5rem;
    font-size: 0.72rem;
    color: var(--muted);
    border-top: 1px solid var(--border);
    font-family: monospace;
  }

  /* ── 响应式 ── */
  @media (max-width: 560px) {
    .term-hero { flex-direction: column; gap: 0.8rem; }
    .term-glyph { font-size: 3rem; text-align: left; }
  }
</style>
</head>
<body>

<header>
  <h1>古汉语考据系统</h1>
  <span class="header-sub">《廣雅疏證》釋詁 · 卷第一上</span>
  <span class="stats-pill" id="stats-bar">加载中…</span>
</header>

<!-- 搜索 -->
<div class="search-wrap">
  <form class="search-form" method="get" action="/">
    <input
      class="search-input"
      name="q"
      id="search-input"
      placeholder="输入汉字检索（如：作、朔、鼻）…"
      value="{{ query or '' }}"
      autofocus
      maxlength="4"
    >
    <button class="search-btn" type="submit">检索</button>
  </form>
</div>

<!-- 快速入口 -->
<div class="quick-row">
  <span class="quick-label">本卷字：</span>
  {%- for ch in quick_chars %}
  <a class="quick-btn" href="/?q={{ ch }}">{{ ch }}</a>
  {%- endfor %}
</div>

<!-- 主内容 -->
<div class="main">

  {% if error %}
    <div class="empty-state" style="color:#a05050">{{ error }}</div>

  {% elif result %}
    <!-- 术语概览 -->
    <div class="term-hero">
      <div class="term-glyph">{{ result.term.term }}</div>
      <div class="term-info">
        <div class="term-core">{{ result.term.core_meaning or result.term.notes }}</div>
        <div class="term-meta-row">
          <span class="badge badge-type">{{ result.term.term_type }}</span>
          <span class="badge badge-cat">{{ result.term.category }}</span>
          {% if result.term.aliases %}
            {% set als = result.term.aliases|from_json %}
            {% if als %}
              <span class="badge badge-cat">通：{{ als|join('、') }}</span>
            {% endif %}
          {% endif %}
          <span class="badge badge-certainty">确定</span>
        </div>
      </div>
    </div>

    <!-- 案例（通用） -->
    {% if result.cases %}
      {% for case in result.cases %}
      <div class="case-card">
        <div class="case-header">
          <span class="case-label">案例</span>
          <span class="case-title">{{ case.title }}</span>
          {% if case.method %}
            <span class="badge badge-type">{{ case.method }}</span>
          {% endif %}
        </div>
        <div class="case-meta">
          {{ case.volume_title }}
          {% if case.section_title %} · {{ case.section_title }}{% endif %}
          {% if case.conclusion %}：
            <span style="color:var(--text); font-style:italic;">{{ case.conclusion }}</span>
          {% endif %}
        </div>
      </div>
      {% endfor %}
    {% endif %}

    <!-- 证据（按类型分组） -->
    {% if result.evidences %}
      {% set ev_groups = result.evidences|groupby('evidence_type') %}
      <div class="evidence-section">
        <div class="ev-group-label">证据（共 {{ result.evidences|length }} 条）</div>

        {# 手工按类型排序展示 #}
        {% set type_order = ['书证', '声训', '义证', '语法证据', '异文', '形证'] %}
        {% set shown_types = [] %}
        {% for ev in result.evidences %}
          {% if ev.evidence_type not in shown_types %}
            {% set _ = shown_types.append(ev.evidence_type) %}
            <div class="ev-group-label" style="border-left:3px solid var(--accent); padding-left:0.5rem; margin-top:0.8rem;">
              {{ ev.evidence_type }}（{{ result.evidences|selectattr('evidence_type','equalto',ev.evidence_type)|list|length }} 条）
            </div>
            {% for ev2 in result.evidences %}
              {% if ev2.evidence_type == ev.evidence_type %}
              <div class="ev-item">
                <span class="ev-badge {{ ev2.evidence_type }}">{{ ev2.evidence_type }}</span>
                <div class="ev-body">
                  {% if ev2.core_snippet %}
                  <div class="ev-core">「{{ ev2.core_snippet }}」</div>
                  {% endif %}
                  {% if ev2.quote_text and ev2.quote_text != ev2.core_snippet %}
                  <div class="ev-full">{{ ev2.quote_text }}</div>
                  {% endif %}
                  <div class="ev-source">{{ ev2.work_title or '未知出处' }}</div>
                  {% if ev2.note %}
                  <div class="ev-note">{{ ev2.note }}</div>
                  {% endif %}
                </div>
              </div>
              {% endif %}
            {% endfor %}
          {% endif %}
        {% endfor %}
      </div>
    {% else %}
      <div class="empty-state" style="padding:2rem 1rem;">
        暂无该字证据记录
      </div>
    {% endif %}

  {% elif query %}
    <div class="empty-state">
      未找到「{{ query }}」的相关记录
      <div class="hint">请尝试输入单字，如：作、朔、鼻、造</div>
    </div>
  {% else %}
    <div class="empty-state">
      请输入汉字开始检索
      <div class="hint">《廣雅疏證》卷第一上 · 釋詁「始也」条</div>
    </div>
  {% endif %}

</div>

<footer>
  古汉语考据系统 · 《廣雅疏證》释诂 · 字 {{ stats.term_count }} · 证据 {{ stats.evidence_count }}
</footer>

<script>
  fetch('/api/stats')
    .then(r => r.json())
    .then(d => {
      document.getElementById('stats-bar').textContent =
        `字 ${d.term_count} | 案例 ${d.case_count} | 证据 ${d.evidence_count}`;
    });
  document.getElementById('search-input').focus();
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  路由
# ═══════════════════════════════════════════════════════════════════════════════

QUICK_CHARS = list("始古昔創作朔鼻方造業乾大君有至善")


def _from_json(s):
    import json as _json
    try:
        return _json.loads(s)
    except Exception:
        return []


@app.context_processor
def inject_helpers():
    return {"from_json": _from_json}


# 注册 from_json 为 Jinja2 filter（用于 |from_json 管道语法）
app.jinja_env.filters["from_json"] = _from_json


@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    result = None
    error = None

    if query:
        try:
            found = db2.search_full(query)
            if found["term"]:
                result = found
        except Exception as ex:
            error = f"检索出错：{ex}"

    return render_template_string(
        TPL,
        query=query,
        result=result,
        error=error,
        quick_chars=QUICK_CHARS,
        stats=db2.stats(),
    )


@app.route("/term/<char>")
def term_page(char: str):
    """单字详情页（备用路由）"""
    try:
        found = db2.search_full(char)
        if not found["term"]:
            return f"<h2>未找到「{char}」</h2><a href='/'>返回</a>", 404
        return render_template_string(
            TPL,
            query=char,
            result=found,
            error=None,
            quick_chars=QUICK_CHARS,
            stats=db2.stats(),
        )
    except Exception as e:
        return f"错误：{e}", 500


@app.route("/api/search")
def api_search():
    """JSON 搜索 API"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "参数 q 不能为空"}), 400
    try:
        return jsonify(db2.search_full(q))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
def api_stats():
    """JSON 统计 API"""
    try:
        return jsonify(db2.stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    st = db2.stats()
    print(f"""
  ╔══════════════════════════════════════╗
  ║   古汉语考据系统 · A方案               ║
  ║   《廣雅疏證》「始也」词条群            ║
  ╠══════════════════════════════════════╣
  ║   字      {st['term_count']:>3}  个                  ║
  ║   案例    {st['case_count']:>3}  条                  ║
  ║   证据    {st['evidence_count']:>3}  条                  ║
  ╚══════════════════════════════════════╝
  检索：http://127.0.0.1:3001
""")
    app.run(debug=False, host="127.0.0.1", port=3001)

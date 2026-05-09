const annotationHeroMeta = document.querySelector('#annotationHeroMeta');
const annotationStatus = document.querySelector('#annotationStatus');
const annotationSearchInput = document.querySelector('#annotationSearchInput');
const annotationDocumentSelect = document.querySelector('#annotationDocumentSelect');
const annotationMethodSelect = document.querySelector('#annotationMethodSelect');
const annotationSearchButton = document.querySelector('#annotationSearchButton');
const annotationResetButton = document.querySelector('#annotationResetButton');
const annotationSummary = document.querySelector('#annotationSummary');
const annotationList = document.querySelector('#annotationList');
const annotationAiInput = document.querySelector('#annotationAiInput');
const annotationAiButton = document.querySelector('#annotationAiButton');
const annotationAiClearButton = document.querySelector('#annotationAiClearButton');
const annotationAiResult = document.querySelector('#annotationAiResult');

const state = {
  snapshot: null,
  query: '',
  document: 'all',
  method: 'all',
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function summarizeText(value, maxLength = 120) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1)}…`;
}

function includesText(values, query) {
  if (!query) return true;
  const needle = query.toLowerCase();
  return values.some((value) => String(value || '').toLowerCase().includes(needle));
}

async function loadSnapshot() {
  const response = await fetch('./data/annotation-snapshot.json');
  if (!response.ok) {
    throw new Error(`annotation-snapshot.json 读取失败：${response.status}`);
  }
  return response.json();
}

function renderAiSources(sources = {}) {
  const annotationCount = sources.annotation?.length || 0;
  const mainCount = sources.main?.length || 0;
  return `
    <div class="annotation-ai-sources">
      <span class="summary-pill">人工库 ${escapeHtml(annotationCount)} 条</span>
      <span class="summary-pill muted">主库补充 ${escapeHtml(mainCount)} 条</span>
    </div>
  `;
}

function parseAiAnswer(answer) {
  const text = String(answer || '')
    .trim()
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '');
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  const candidates = [
    text,
    start >= 0 && end > start ? text.slice(start, end + 1) : '',
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === 'object') return parsed;
    } catch {
      continue;
    }
  }

  return null;
}

function renderAiSection(title, content) {
  const items = Array.isArray(content) ? content.filter(Boolean) : [content].filter(Boolean);
  if (!items.length) return '';
  return `
    <section class="annotation-ai-section">
      <h3>${escapeHtml(title)}</h3>
      ${items.length === 1
        ? `<p>${escapeHtml(items[0])}</p>`
        : `<ol>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>`}
    </section>
  `;
}

function renderAiAnswer(answer, structuredAnswer = null) {
  const structured = structuredAnswer || parseAiAnswer(answer);
  if (!structured) {
    return `<pre>${escapeHtml(answer || '未返回内容')}</pre>`;
  }

  return `
    <div class="annotation-ai-report">
      ${renderAiSection('判断', structured.judgment)}
      ${renderAiSection('可用证据', structured.evidences)}
      ${renderAiSection('解析草案', structured.draft)}
      ${renderAiSection('仍需人工核对处', structured.reviewNotes)}
    </div>
  `;
}

async function runAnnotationAi() {
  const question = annotationAiInput?.value.trim() || '';
  if (!question) {
    annotationAiResult.innerHTML = '<p class="compact-note">请输入需要解析的内容。</p>';
    return;
  }

  annotationAiButton.disabled = true;
  annotationAiResult.innerHTML = '<p class="compact-note">正在检索人工库并调用 AI...</p>';

  try {
    const response = await fetch('/api/ai/annotation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const payload = await response.json();

    if (!payload.ok) {
      annotationAiResult.innerHTML = `
        <p class="compact-note">${escapeHtml(payload.message || 'AI 解析失败')}</p>
        ${renderAiSources(payload.sources)}
      `;
      return;
    }

    annotationAiResult.innerHTML = `
      ${renderAiSources(payload.sources)}
      ${renderAiAnswer(payload.answer, payload.structuredAnswer)}
    `;
  } catch (error) {
    annotationAiResult.innerHTML = `<p class="compact-note">AI 接口不可用：${escapeHtml(error.message)}</p>`;
  } finally {
    annotationAiButton.disabled = false;
  }
}

function renderHero() {
  const counts = state.snapshot?.counts || {};
  const items = [
    { label: '来源', value: state.snapshot?.sourceLabel || '人工标注灰度库' },
    { label: '文档', value: `${counts.documents || 0} 件` },
    { label: '案例', value: `${counts.cases || 0} 条` },
    { label: '证据', value: `${counts.evidences || 0} 条` },
  ];

  annotationHeroMeta.innerHTML = items
    .map((item) => `
      <div class="hero-panel-item">
        <span class="hero-kicker">${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </div>
    `)
    .join('');
}

function renderFilters() {
  const documents = Object.keys(state.snapshot.documentCounts || {}).sort();
  const methods = Object.keys(state.snapshot.methodCounts || {}).sort();

  annotationDocumentSelect.innerHTML = [
    '<option value="all">全部文档</option>',
    ...documents.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}（${escapeHtml(state.snapshot.documentCounts[name])}）</option>`),
  ].join('');

  annotationMethodSelect.innerHTML = [
    '<option value="all">全部方法</option>',
    ...methods.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}（${escapeHtml(state.snapshot.methodCounts[name])}）</option>`),
  ].join('');
}

function caseSearchValues(item) {
  return [
    item.case_title,
    item.source_work,
    item.target_work,
    item.target_text,
    item.problem,
    item.claim,
    item.conclusion,
    item.certainty,
    item.status,
    ...(item.method_tags || []),
    ...(item.terms || []).flatMap((term) => [term.term, term.related_term, term.relation_type, term.note]),
    ...(item.evidences || []).flatMap((evidence) => [evidence.evidence_type, evidence.work, evidence.quote, evidence.role]),
    ...(item.process_steps || []).flatMap((step) => [step.step_type, step.text]),
  ];
}

function filterCases() {
  const query = state.query.trim();
  return (state.snapshot.cases || []).filter((item) => {
    const docName = item.source_document?.source_file_name || '未标注文档';
    const methodOk = state.method === 'all' || (item.method_tags || []).includes(state.method);
    const documentOk = state.document === 'all' || docName === state.document;
    return methodOk && documentOk && includesText(caseSearchValues(item), query);
  });
}

function isTermGroupCase(item) {
  return item.source_document?.doc_type === 'term_group_blocks';
}

function cleanSubcaseTitle(value) {
  return String(value || '')
    .replace(/^[\s\d①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳\-－—~～至、.．]+/, '')
    .replace(/\s+/g, '')
    .trim();
}

function extractSubcaseTerms(title) {
  return cleanSubcaseTitle(title)
    .split(/[、，,\/／]/)
    .map((term) => term.trim())
    .filter(Boolean);
}

function evidenceMatchesTerms(evidence, terms) {
  if (!terms.length) return false;
  const haystack = [
    evidence.term,
    evidence.quote,
    evidence.work,
    evidence.role,
  ].join(' ');

  return terms.some((term) => term && haystack.includes(term));
}

function buildSubcases(item) {
  if (!isTermGroupCase(item)) return [];

  const evidences = item.evidences || [];
  return (item.process_steps || [])
    .filter((step) => !['立论', '结论'].includes(step.step_type))
    .map((step, index) => {
      const [rawTitle, ...rest] = String(step.text || '').split('：');
      const title = cleanSubcaseTitle(rawTitle || `子单元 ${index + 1}`);
      const terms = extractSubcaseTerms(rawTitle);
      const description = rest.join('：').trim() || step.text || '';
      const matchedEvidences = evidences.filter((evidence) => evidenceMatchesTerms(evidence, terms));

      return {
        title,
        terms,
        description,
        stepType: step.step_type || '释词',
        evidences: matchedEvidences,
      };
    });
}

function renderSubcases(item) {
  const subcases = buildSubcases(item);
  if (!subcases.length) return '';

  return `
    <section class="annotation-subcase-panel">
      <div class="annotation-subcase-head">
        <div>
          <p class="section-kicker">父案例下的子单元</p>
          <h4>按现有过程步骤拆出的词群论证</h4>
        </div>
        <span class="summary-pill">${escapeHtml(subcases.length)} 个子单元</span>
      </div>
      <div class="annotation-subcase-grid">
        ${subcases.map((subcase) => `
          <details class="annotation-subcase">
            <summary>
              <span>
                <em>${escapeHtml(subcase.stepType)}</em>
                <strong>${escapeHtml(subcase.title || '未命名子单元')}</strong>
              </span>
              <small>${escapeHtml(subcase.evidences.length)} 条关联证据</small>
            </summary>
            <div class="annotation-subcase-body">
              <p>${escapeHtml(subcase.description || '暂无说明')}</p>
              <div class="annotation-chip-list">
                ${subcase.terms.length ? subcase.terms.map((term) => `<span class="annotation-chip">${escapeHtml(term)}</span>`).join('') : '<span class="compact-note">未抽出字词</span>'}
              </div>
              <div class="annotation-subcase-evidence">
                ${subcase.evidences.length ? subcase.evidences.slice(0, 4).map((evidence) => `
                  <blockquote class="annotation-quote compact">
                    <p>${escapeHtml(evidence.quote || '未录引文')}</p>
                    <footer>${escapeHtml(evidence.work || '未标注来源')} · ${escapeHtml(evidence.role || evidence.evidence_type || '')}</footer>
                  </blockquote>
                `).join('') : '<p class="compact-note">当前快照未能按字词自动匹配证据，仍可在“原始标注结构”中查看全部证据。</p>'}
              </div>
            </div>
          </details>
        `).join('')}
      </div>
    </section>
  `;
}

function renderCase(item) {
  const docName = item.source_document?.source_file_name || '未标注文档';
  const terms = item.terms || [];
  const evidences = item.evidences || [];
  const steps = item.process_steps || [];

  return `
    <article class="card annotation-card">
      <div class="annotation-card-head">
        <div>
          <p class="section-kicker">${escapeHtml(docName)}</p>
          <h3>${escapeHtml(item.case_title || '未题名案例')}</h3>
        </div>
        <div class="case-tags">
          ${isTermGroupCase(item) ? '<span class="tag strong">父案例</span>' : ''}
          ${(item.method_tags || ['未标注方法']).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
          <span class="tag muted">${escapeHtml(item.certainty || '待核')}</span>
        </div>
      </div>

      <div class="annotation-raw-grid">
        <p><strong>来源著作</strong><span>${escapeHtml(item.source_work || '未标注')}</span></p>
        <p><strong>目标文本</strong><span>${escapeHtml(summarizeText(item.target_text, 90) || '未标注')}</span></p>
        <p><strong>状态</strong><span>${escapeHtml(item.status || '草稿')}</span></p>
      </div>

      <p class="case-summary">${escapeHtml(summarizeText(item.problem || item.claim || item.conclusion, 180))}</p>

      ${renderSubcases(item)}

      <details class="fold-card annotation-fold">
        <summary>展开原始标注结构</summary>
        <div class="fold-body annotation-fold-body">
          <section>
            <h4>判断</h4>
            <p><strong>问题：</strong>${escapeHtml(item.problem || '未标注')}</p>
            <p><strong>主张：</strong>${escapeHtml(item.claim || '未标注')}</p>
            <p><strong>结论：</strong>${escapeHtml(item.conclusion || '未标注')}</p>
          </section>

          <section>
            <h4>相关字词</h4>
            <div class="annotation-chip-list">
              ${terms.length ? terms.map((term) => `
                <span class="annotation-chip">
                  ${escapeHtml(term.term || '')}
                  ${term.related_term ? `→ ${escapeHtml(term.related_term)}` : ''}
                  <em>${escapeHtml(term.relation_type || term.term_type || '')}</em>
                </span>
              `).join('') : '<span class="compact-note">暂无字词标注</span>'}
            </div>
          </section>

          <section>
            <h4>证据</h4>
            ${evidences.length ? evidences.map((evidence) => `
              <blockquote class="annotation-quote">
                <p>${escapeHtml(evidence.quote || '未录引文')}</p>
                <footer>${escapeHtml(evidence.evidence_type || '证据')} · ${escapeHtml(evidence.work || '未标注来源')} · ${escapeHtml(evidence.role || '')}</footer>
              </blockquote>
            `).join('') : '<p class="compact-note">暂无证据标注</p>'}
          </section>

          <section>
            <h4>过程步骤</h4>
            <ol class="annotation-step-list">
              ${steps.length ? steps.map((step) => `
                <li>
                  <strong>${escapeHtml(step.step_type || `步骤 ${step.step_order}`)}</strong>
                  <span>${escapeHtml(step.text || '')}</span>
                </li>
              `).join('') : '<li>暂无过程步骤</li>'}
            </ol>
          </section>
        </div>
      </details>
    </article>
  `;
}

function render() {
  const items = filterCases();

  annotationSummary.innerHTML = `
    <div class="summary-row summary-row-meta">
      <span class="summary-pill">结果：${escapeHtml(items.length)} / ${escapeHtml((state.snapshot.cases || []).length)} 条</span>
      <span class="summary-pill muted">文档：${escapeHtml(state.document === 'all' ? '全部' : state.document)}</span>
      <span class="summary-pill muted">方法：${escapeHtml(state.method === 'all' ? '全部' : state.method)}</span>
      ${state.query ? `<span class="summary-pill muted">关键词：${escapeHtml(state.query)}</span>` : ''}
    </div>
  `;

  annotationList.innerHTML = items.length
    ? items.map(renderCase).join('')
    : '<article class="card"><h3>暂无匹配的人工标注记录</h3><p>请更换关键词、来源文档或方法标签。</p></article>';
}

async function init() {
  try {
    state.snapshot = await loadSnapshot();
    annotationStatus.textContent = `灰度库来源：${state.snapshot.description || state.snapshot.sourceLabel}`;
    renderHero();
    renderFilters();
    render();
  } catch (error) {
    annotationStatus.textContent = error.message;
    annotationList.innerHTML = '<article class="card"><h3>人工标注库读取失败</h3><p>请先运行 npm run sync:annotation 生成快照。</p></article>';
  }
}

annotationSearchButton?.addEventListener('click', () => {
  state.query = annotationSearchInput.value.trim();
  state.document = annotationDocumentSelect.value || 'all';
  state.method = annotationMethodSelect.value || 'all';
  render();
});

annotationResetButton?.addEventListener('click', () => {
  state.query = '';
  state.document = 'all';
  state.method = 'all';
  annotationSearchInput.value = '';
  annotationDocumentSelect.value = 'all';
  annotationMethodSelect.value = 'all';
  render();
});

annotationSearchInput?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    annotationSearchButton.click();
  }
});

annotationAiButton?.addEventListener('click', runAnnotationAi);

annotationAiClearButton?.addEventListener('click', () => {
  annotationAiInput.value = '';
  annotationAiResult.textContent = '尚未解析。';
});

init();

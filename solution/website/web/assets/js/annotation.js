const annotationHeroMeta = document.querySelector('#annotationHeroMeta');
const annotationStatus = document.querySelector('#annotationStatus');
const annotationSearchInput = document.querySelector('#annotationSearchInput');
const annotationAnnotatorFilters = document.querySelector('#annotationAnnotatorFilters');
const annotationOriginFilters = document.querySelector('#annotationOriginFilters');
const annotationSearchButton = document.querySelector('#annotationSearchButton');
const annotationSummary = document.querySelector('#annotationSummary');
const annotationList = document.querySelector('#annotationList');
const annotationFilterSummary = document.querySelector('#annotationFilterSummary');
const annotationQuickSearches = document.querySelector('#annotationQuickSearches');

const QUICK_SEARCHES = [
  { label: '案例 · 薄言有之', query: '薄言有之' },
  { label: '方法 · 校勘', query: '校勘' },
  { label: '字词 · 允', query: '允' },
  { label: '证据 · 广雅', query: '广雅' },
  { label: '简繁 · 终风且暴', query: '终风且暴' },
  { label: '待补 · 未抽取', query: '未抽取' },
];

const state = {
  bootstrap: null,
  indexItems: [],
  query: '',
  annotators: [],
  origins: [],
  page: 1,
  pageSize: 50,
};

const annotationDetailCache = new Map();

async function requestJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`人工标注库 API 读取失败：${response.status}`);
  }
  return response.json();
}

function escapeRegExp(value) {
  return String(value || '').replace(/[\^$.*+?()[\]{}|]/g, '\\$&');
}

function highlightText(value, query = state.query) {
  const text = String(value || '');
  const escaped = escapeHtml(text);
  const needle = String(query || '').trim().toLowerCase();
  if (!needle) return escaped;
  const pattern = new RegExp(escapeRegExp(escapeHtml(needle)), 'gi');
  return escaped.replace(pattern, (match) => '<mark class="search-hit">' + match + '</mark>');
}

function compareLocalCaseIds(left, right) {
  const leftId = Number(left.id);
  const rightId = Number(right.id);
  if (Number.isFinite(leftId) && Number.isFinite(rightId)) return leftId - rightId;
  return String(left.id || '').localeCompare(String(right.id || ''), 'zh-CN', { numeric: true });
}

function buildLocalResult() {
  const query = String(state.query || '').trim().toLowerCase();
  const origins = new Set(state.origins);
  const annotators = new Set(state.annotators);
  const allItems = state.indexItems
    .filter((item) => {
      const originOk = !origins.size || origins.has(item.origin);
      const annotatorOk = !annotators.size || annotators.has(item.annotator);
      const queryOk = !query || String(item.search_text || '').includes(query);
      return originOk && annotatorOk && queryOk;
    })
    .sort(compareLocalCaseIds);
  const total = allItems.length;
  const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
  const page = Math.min(state.page, totalPages);
  const start = (page - 1) * state.pageSize;
  return {
    ok: true,
    query: state.query,
    origin: state.origins.length === 1 ? state.origins[0] : 'all',
    origins: state.origins,
    annotator: state.annotators.length === 1 ? state.annotators[0] : 'all',
    annotators: state.annotators,
    total,
    page,
    pageSize: state.pageSize,
    totalPages,
    items: allItems.slice(start, start + state.pageSize),
    counts: state.bootstrap?.counts || {},
  };
}

function renderHero() {
  const counts = state.bootstrap?.counts || {};
  const items = [
    { label: '来源', value: state.bootstrap?.sourceLabel || '人工标注灰度库' },
    { label: '文档', value: `${counts.documents || 0} 件` },
    { label: '案例', value: `${counts.cases || 0} 条` },
    { label: '证据', value: `${counts.evidences || 0} 条` },
  ];

  BrowserCommon.renderHeroItems(annotationHeroMeta, items);
}

function renderMultiFilters(target, items, activeValues, dataAttribute) {
  if (!target) return;
  const selected = new Set(activeValues);
  target.innerHTML = (items || []).map((item) => {
    const isAll = item.value === 'all';
    const checked = isAll ? selected.size === 0 : selected.has(item.value);
    return `
      <label class="annotation-filter-option${checked ? ' is-selected' : ''}">
        <input type="checkbox" value="${escapeHtml(item.value)}" data-${dataAttribute} ${checked ? 'checked' : ''} />
        <span class="annotation-filter-option-label">${escapeHtml(item.label)}</span>
        <span class="annotation-filter-count">${escapeHtml(String(item.count || 0))}</span>
      </label>
    `;
  }).join('');
}

function renderFilters() {
  renderMultiFilters(annotationOriginFilters, state.bootstrap?.origins, state.origins, 'annotation-origin');
  renderMultiFilters(annotationAnnotatorFilters, state.bootstrap?.annotators, state.annotators, 'annotation-annotator');
  const selectedCount = state.origins.length + state.annotators.length;
  if (annotationFilterSummary) annotationFilterSummary.textContent = selectedCount ? `已选 ${selectedCount} 项` : '未筛选';
}

function renderQuickSearches() {
  if (!annotationQuickSearches) return;
  annotationQuickSearches.innerHTML = [
    '<span class="annotation-quick-search-label">快捷检索</span>',
    '<div class="annotation-quick-search-list">',
    QUICK_SEARCHES.map((item) => (
      '<button type="button" class="annotation-quick-search" data-annotation-quick-query="'
      + escapeHtml(item.query)
      + '">'
      + escapeHtml(item.label)
      + '</button>'
    )).join(''),
    '</div>',
  ].join('');
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
              <p>${highlightText(subcase.description || '暂无说明')}</p>
              <div class="annotation-chip-list">
                ${subcase.terms.length ? subcase.terms.map((term) => `<span class="annotation-chip">${highlightText(term)}</span>`).join('') : '<span class="compact-note">未抽出字词</span>'}
              </div>
              <div class="annotation-subcase-evidence">
                ${subcase.evidences.length ? subcase.evidences.slice(0, 4).map((evidence) => `
                  <blockquote class="annotation-quote compact">
                        <p>${highlightText(evidence.quote || '未录引文')}</p>
                        <footer>${highlightText(evidence.work || '未标注来源')} · ${highlightText(evidence.role || evidence.evidence_type || '')}</footer>
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
  const detailLoaded = item.detail_loaded === true;

  return `
    <article class="card annotation-card" data-case-id="${escapeHtml(item.id)}">
      <div class="annotation-card-head">
        <div>
          <p class="section-kicker">${escapeHtml(docName)}</p>
          <h3>${highlightText(item.case_title || '未题名案例')}</h3>
        </div>
        <div class="case-tags">
          ${isTermGroupCase(item) ? '<span class="tag strong">父案例</span>' : ''}
          ${(item.method_tags || ['未标注方法']).map((tag) => `<span class="tag">${highlightText(tag)}</span>`).join('')}
          <span class="tag muted">${escapeHtml(item.certainty || '待核')}</span>
        </div>
      </div>

      <div class="annotation-target-card">
        <strong>目标文本</strong>
        <span>${highlightText(summarizeText(item.target_text, 180) || '未标注')}</span>
      </div>

      <p class="case-summary">${highlightText(summarizeText(item.problem || item.claim || item.conclusion, 180))}</p>

      ${detailLoaded ? renderSubcases(item) : ''}

      <details class="fold-card annotation-fold" data-annotation-detail-id="${escapeHtml(item.id)}" data-detail-loaded="${detailLoaded}">
        <summary>展开原始标注结构</summary>
        <p class="compact-note annotation-detail-placeholder">展开后读取完整标注结构</p>
        <div class="fold-body annotation-fold-body">
          <div class="annotation-detail-content">
          <section>
            <h4>判断</h4>
            <p><strong>问题：</strong>${highlightText(item.problem || '未标注')}</p>
            <p><strong>主张：</strong>${highlightText(item.claim || '未标注')}</p>
            <p><strong>结论：</strong>${highlightText(item.conclusion || '未标注')}</p>
          </section>

          <section>
            <h4>相关字词</h4>
            <div class="annotation-chip-list">
              ${terms.length ? terms.map((term) => `
                <span class="annotation-chip">
                  ${highlightText(term.term || '')}
                  ${term.related_term ? `→ ${highlightText(term.related_term)}` : ''}
                  <em>${highlightText(term.relation_type || term.term_type || '')}</em>
                </span>
              `).join('') : '<span class="compact-note">暂无字词标注</span>'}
            </div>
          </section>

          <section>
            <h4>证据</h4>
            ${evidences.length ? evidences.map((evidence) => `
              <blockquote class="annotation-quote">
                <p>${highlightText(evidence.quote || '未录引文')}</p>
                <footer>${highlightText(evidence.evidence_type || '证据')} · ${highlightText(evidence.work || '未标注来源')} · ${highlightText(evidence.role || '')}</footer>
              </blockquote>
            `).join('') : '<p class="compact-note">暂无证据标注</p>'}
          </section>

          <section>
            <h4>过程步骤</h4>
            <ol class="annotation-step-list">
              ${steps.length ? steps.map((step) => `
                <li>
                  <strong>${highlightText(step.step_type || `步骤 ${step.step_order}`)}</strong>
                  <span>${highlightText(step.text || '')}</span>
                </li>
              `).join('') : '<li>暂无过程步骤</li>'}
            </ol>
          </section>
        </div>
        </div>
      </details>
    </article>
  `;
}

function renderGroupedResults(items) {
  const groups = new Map();
  items.forEach((item) => {
    const origin = item.origin || item.source_work || '未标注出处';
    if (!groups.has(origin)) groups.set(origin, []);
    groups.get(origin).push(item);
  });

  const configuredOrder = (state.bootstrap?.origins || [])
    .map((item) => item.value)
    .filter((value) => value !== 'all');
  const orderedOrigins = [
    ...configuredOrder.filter((origin) => groups.has(origin)),
    ...[...groups.keys()].filter((origin) => !configuredOrder.includes(origin)),
  ];

  return orderedOrigins.map((origin) => `
    <section class="annotation-origin-group">
      <div class="annotation-origin-heading">
        <h3>${escapeHtml(origin)}</h3>
        <span class="summary-pill muted">${escapeHtml(groups.get(origin).length)} 条</span>
      </div>
      <div class="annotation-list annotation-origin-list">
        ${groups.get(origin).map(renderCase).join('')}
      </div>
    </section>
  `).join('');
}

function render(result) {
  const items = result.items || [];

  annotationSummary.innerHTML = `
    <div class="summary-row summary-row-meta">
      <span class="summary-pill">结果：${escapeHtml(result.total || 0)} / ${escapeHtml(state.bootstrap?.counts?.cases || 0)} 条</span>
      ${state.query ? `<span class="summary-pill muted">关键词：${escapeHtml(state.query)}</span>` : ''}
    </div>
  `;

  annotationList.innerHTML = items.length
    ? renderGroupedResults(items)
    : '<article class="card"><h3>暂无匹配的人工标注记录</h3><p>请更换关键词或左侧筛选条件。</p></article>';
}

async function runAnnotationBrowse() {
  const result = buildLocalResult();
  annotationStatus.textContent = state.query
    ? '关键词“' + state.query + '”找到 ' + (result.total || 0) + ' 条（本地检索）。'
    : '人工标注库已连接 · 当前显示 ' + (result.total || 0) + ' 条。';
  render(result);
}

async function init() {
  try {
    state.bootstrap = await requestJson('/api/annotation/index');
    state.indexItems = state.bootstrap.items || [];
    annotationStatus.textContent = '这里只浏览人工标注与 AI 整理后的结构化数据，与主数据库并行。';
    renderHero();
    renderFilters();
    renderQuickSearches();
    await runAnnotationBrowse();
  } catch (error) {
    annotationStatus.textContent = error.message;
    annotationList.innerHTML = '<article class="card"><h3>人工标注库读取失败</h3><p>请先运行 npm --prefix solution/website run sync:annotation 生成快照。</p></article>';
  }
}

annotationSearchButton?.addEventListener('click', async () => {
  state.query = String(annotationSearchInput?.value || '').trim();
  state.page = 1;
  await runAnnotationBrowse();
});

annotationSearchInput?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    annotationSearchButton.click();
  }
});

annotationQuickSearches?.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-annotation-quick-query]');
  if (!button) return;
  state.query = button.dataset.annotationQuickQuery || '';
  if (annotationSearchInput) annotationSearchInput.value = state.query;
  state.page = 1;
  await runAnnotationBrowse();
});

async function loadAnnotationDetail(details) {
  if (!details?.open || details.dataset.detailLoaded === 'true') return;
  const id = details.dataset.annotationDetailId;
  const card = details.closest('.annotation-card');
  const baseItem = state.indexItems.find((item) => String(item.id) === String(id));
  if (!id || !card || !baseItem) return;
  const placeholder = details.querySelector('.annotation-detail-placeholder');
  if (placeholder) placeholder.textContent = '正在读取完整标注结构……';
  try {
    let detail = annotationDetailCache.get(String(id));
    if (!detail) {
      const payload = await requestJson('/api/annotation/detail?id=' + encodeURIComponent(id));
      detail = payload.item;
      annotationDetailCache.set(String(id), detail);
    }
    const fragment = document.createRange().createContextualFragment(
      renderCase({ ...baseItem, ...detail, detail_loaded: true }),
    );
    const replacement = fragment.firstElementChild;
    card.replaceWith(replacement);
    const replacementDetails = replacement.querySelector('[data-annotation-detail-id]');
    if (replacementDetails) replacementDetails.open = true;
  } catch (error) {
    if (placeholder) placeholder.textContent = '完整标注读取失败：' + error.message;
  }
}

annotationList?.addEventListener('click', (event) => {
  const summary = event.target.closest('summary');
  const details = summary?.parentElement;
  if (!details?.dataset.annotationDetailId) return;
  setTimeout(() => loadAnnotationDetail(details), 0);
});

async function toggleFilter(group, value) {
  if (value === 'all') {
    state[group] = [];
  } else if (state[group].includes(value)) {
    state[group] = state[group].filter((item) => item !== value);
  } else {
    state[group] = [...state[group], value];
  }
  state.page = 1;
  renderFilters();
  await runAnnotationBrowse();
}

annotationAnnotatorFilters?.addEventListener('change', (event) => {
  const input = event.target.closest('[data-annotation-annotator]');
  if (input) toggleFilter('annotators', input.value);
});

annotationOriginFilters?.addEventListener('change', (event) => {
  const input = event.target.closest('[data-annotation-origin]');
  if (input) toggleFilter('origins', input.value);
});

init();

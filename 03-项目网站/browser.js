const browserNav = document.querySelector('#browserNav');
const browserFilters = document.querySelector('#browserFilters');
const browserStatus = document.querySelector('#browserStatus');
const browserHeading = document.querySelector('#browserHeading');
const browserSearchInput = document.querySelector('#browserSearchInput');
const browserModeSelect = document.querySelector('#browserModeSelect');
const browserSearchButton = document.querySelector('#browserSearchButton');
const browserResetButton = document.querySelector('#browserResetButton');
const browserSummary = document.querySelector('#browserSummary');
const browserPresets = document.querySelector('#browserPresets');
const browserList = document.querySelector('#browserList');
const browserListSection = document.querySelector('#browserListSection');
const browserSchemaSection = document.querySelector('#browserSchemaSection');
const browserSchemaSummary = document.querySelector('#browserSchemaSummary');
const browserStats = document.querySelector('#browserStats');
const browserSchemaGrid = document.querySelector('#browserSchemaGrid');
const browserHeroMeta = document.querySelector('#browserHeroMeta');
const browserPagination = document.querySelector('#browserPagination');

const state = {
  view: 'terms',
  category: 'all',
  mode: 'entry',
  query: '',
  page: 1,
  pageSize: 20,
  bootstrap: null,
};

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function requestJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function summarizeText(value, maxLength = 88) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) {
    return '';
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1)}…`;
}

function highlightText(text, keyword) {
  const raw = String(text || '');
  const query = String(keyword || '').trim();
  if (!query) {
    return escapeHtml(raw);
  }

  const pattern = new RegExp(`(${escapeRegExp(query)})`, 'ig');
  return escapeHtml(raw).replace(pattern, '<mark class="match-mark">$1</mark>');
}

function buildMatchSnippet(candidates, keyword) {
  const query = String(keyword || '').trim().toLowerCase();
  if (!query) {
    return '';
  }

  const matchSource = candidates.find((item) => String(item || '').toLowerCase().includes(query));
  if (!matchSource) {
    return '';
  }

  const source = String(matchSource).replace(/\s+/g, ' ').trim();
  const matchIndex = source.toLowerCase().indexOf(query);
  const start = Math.max(0, matchIndex - 20);
  const end = Math.min(source.length, matchIndex + query.length + 24);
  const snippet = `${start > 0 ? '…' : ''}${source.slice(start, end)}${end < source.length ? '…' : ''}`;
  return highlightText(snippet, keyword);
}

function buildTermHref(id) {
  return `./term.html?id=${encodeURIComponent(String(id))}`;
}

function buildCaseHref(id) {
  return `./case.html?id=${encodeURIComponent(String(id))}`;
}

function syncUrl() {
  const params = new URLSearchParams();
  params.set('view', state.view);
  if (state.category && state.category !== 'all') {
    params.set('category', state.category);
  }
  if (state.mode && state.mode !== 'entry') {
    params.set('mode', state.mode);
  }
  if (state.query) {
    params.set('q', state.query);
  }
  if (state.page > 1) {
    params.set('page', String(state.page));
  }
  history.replaceState(null, '', `./database.html?${params.toString()}`);
}

function loadUrlState() {
  const params = new URLSearchParams(window.location.search);
  const view = params.get('view');
  const category = params.get('category');
  const mode = params.get('mode');
  const query = params.get('q');
  const page = Number.parseInt(params.get('page') || '', 10);

  if (view === 'cases' || view === 'schema') {
    state.view = view;
  }
  if (category) {
    state.category = category;
  }
  if (mode === 'fulltext') {
    state.mode = 'fulltext';
  }
  if (query) {
    state.query = query;
  }
  if (Number.isFinite(page) && page > 0) {
    state.page = page;
  }
}

function renderHeroMeta() {
  if (!browserHeroMeta || !state.bootstrap) return;

  const counts = state.bootstrap.counts || {};
  const items = [
    { label: '字词', value: `${counts.terms || 0} 条` },
    { label: '案例', value: `${counts.cases || 0} 条` },
    { label: '来源', value: state.bootstrap.sourceLabel || '未知' },
  ];

  browserHeroMeta.innerHTML = items
    .map(
      (item) => `
        <div class="hero-panel-item">
          <span class="hero-kicker">${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
        </div>
      `,
    )
    .join('');
}

function renderStats(counts) {
  if (!browserStats) return;

  const items = [
    { label: '著作', value: counts.works ?? 0 },
    { label: '片段', value: counts.passages ?? 0 },
    { label: '词条', value: counts.terms ?? 0 },
    { label: '案例', value: counts.cases ?? 0 },
    { label: '证据', value: counts.evidences ?? 0 },
  ];

  browserStats.innerHTML = items
    .map(
      (item) => `
        <div class="stat-card">
          <div class="value">${item.value}</div>
          <div class="label">${item.label}</div>
        </div>
      `,
    )
    .join('');
}

function renderSchema(stores) {
  if (!browserSchemaGrid) return;

  browserSchemaGrid.innerHTML = (stores || [])
    .map(
      (store) => `
        <article class="card">
          <h3>${escapeHtml(store.label)}</h3>
          <p>${escapeHtml(store.purpose)}</p>
          <div class="schema-meta">
            ${store.keyFields.map((field) => `<span class="tag muted">${escapeHtml(field)}</span>`).join('')}
            ${store.indexes.map((field) => `<span class="tag">idx:${escapeHtml(field)}</span>`).join('')}
          </div>
          <p class="db-status">当前记录：${escapeHtml(String(store.count || 0))} 条</p>
        </article>
      `,
    )
    .join('');
}

function getCurrentCategories() {
  if (!state.bootstrap) {
    return [];
  }

  if (state.view === 'schema') {
    return [{ value: 'all', label: '架构总览', count: state.bootstrap.stores?.length || 0 }];
  }

  return state.view === 'cases' ? state.bootstrap.caseCategories || [] : state.bootstrap.termCategories || [];
}

function renderSidebar() {
  if (!state.bootstrap) return;

  const views = state.bootstrap.views || [];
  browserNav.innerHTML = views
    .map(
      (item) => `
        <button class="sidebar-button${state.view === item.value ? ' active' : ''}" type="button" data-view="${escapeHtml(item.value)}">
          <span>${escapeHtml(item.label)}</span>
          <span class="tag muted">${escapeHtml(String(item.count))}</span>
        </button>
      `,
    )
    .join('') || '<p class="compact-note sidebar-empty">暂无可用浏览类别。</p>';

  const categories = getCurrentCategories();
  if (!categories.some((item) => item.value === state.category)) {
    state.category = 'all';
  }
  browserFilters.innerHTML = categories
    .map(
      (item) => `
        <button class="filter-chip${state.category === item.value ? ' active' : ''}" type="button" data-category="${escapeHtml(item.value)}">
          ${escapeHtml(item.label)}
          <span>${escapeHtml(String(item.count))}</span>
        </button>
      `,
    )
    .join('') || '<p class="compact-note sidebar-empty">当前分类为空。</p>';
}

function renderSummary(result) {
  if (!browserSummary) return;

  const categoryLabel = getCurrentCategories().find((item) => item.value === state.category)?.label || '全部';

  browserSummary.innerHTML = `
    <div class="summary-row">
      <div class="summary-block">
        <span class="summary-label">浏览视图</span>
        <div class="summary-group" aria-label="数据库视图">
          <button class="summary-pill summary-pill-button${state.view === 'terms' ? ' active' : ''}" type="button" data-summary-view="terms">字词</button>
          <button class="summary-pill summary-pill-button${state.view === 'cases' ? ' active' : ''}" type="button" data-summary-view="cases">考据案例</button>
          <button class="summary-pill summary-pill-button${state.view === 'schema' ? ' active' : ''}" type="button" data-summary-view="schema">结构</button>
        </div>
      </div>
      <div class="summary-block">
        <span class="summary-label">检索方式</span>
        <div class="summary-group" aria-label="检索方式">
          <button class="summary-pill summary-pill-button${state.mode === 'entry' ? ' active' : ''}" type="button" data-summary-mode="entry">条目检索</button>
          <button class="summary-pill summary-pill-button${state.mode === 'fulltext' ? ' active' : ''}" type="button" data-summary-mode="fulltext">正文检索</button>
        </div>
      </div>
    </div>
    <div class="summary-row summary-row-meta">
      <span class="summary-pill muted">当前分类：${escapeHtml(categoryLabel)}</span>
      <button class="summary-pill summary-pill-button muted" type="button" data-summary-action="result">结果：${escapeHtml(String(result.total || 0))} 条</button>
    </div>
  `;
}

function renderPagination(result) {
  if (!browserPagination) return;

  const total = Number(result.total || 0);
  const totalPages = Number(result.totalPages || 1);
  const currentPage = Number(result.page || 1);

  if (state.view === 'schema' || totalPages <= 1) {
    browserPagination.innerHTML = '';
    browserPagination.hidden = true;
    return;
  }

  const pageButtons = [];
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);

  for (let page = start; page <= end; page += 1) {
    pageButtons.push(`
      <button class="pagination-button${page === currentPage ? ' active' : ''}" type="button" data-page="${page}">
        ${escapeHtml(String(page))}
      </button>
    `);
  }

  browserPagination.hidden = false;
  browserPagination.innerHTML = `
    <div class="card pagination-card">
      <div class="pagination-meta">
        <span>每页 20 条</span>
        <span>第 ${escapeHtml(String(currentPage))} / ${escapeHtml(String(totalPages))} 页</span>
        <span>共 ${escapeHtml(String(total))} 条</span>
      </div>
      <div class="pagination-controls">
        <button class="pagination-button" type="button" data-page-action="prev" ${currentPage <= 1 ? 'disabled' : ''}>上一页</button>
        ${pageButtons.join('')}
        <button class="pagination-button" type="button" data-page-action="next" ${currentPage >= totalPages ? 'disabled' : ''}>下一页</button>
      </div>
      <form id="browserPaginationForm" class="pagination-jump">
        <label for="browserPageInput">页码</label>
        <input id="browserPageInput" type="number" min="1" max="${escapeHtml(String(totalPages))}" value="${escapeHtml(String(currentPage))}" />
        <button class="pagination-button" type="submit">跳转</button>
      </form>
    </div>
  `;
}

function renderTermResults(items) {
  if (!items.length) {
    browserList.innerHTML = '<article class="card"><h3>暂无符合条件的字词记录</h3><p>请更换字词、义项或引文关键词继续检索。</p></article>';
    return;
  }

  browserList.innerHTML = items
    .map(
      (item) => `
        <article class="card term-card browser-card">
          <div class="term-card-top">
            <a class="term-glyph term-glyph-link" href="${buildTermHref(item.id)}">${escapeHtml(item.term)}</a>
            <div class="term-meta-stack">
              <div class="case-tags">
                <span class="tag">${escapeHtml(item.termType || '未分类')}</span>
                <span class="tag muted">${escapeHtml(item.category || '未分类')}</span>
              </div>
              <p class="compact-note">关联案例 ${escapeHtml(String(item.caseCount || 0))} 条</p>
            </div>
          </div>
          <p class="term-core">${escapeHtml(summarizeText(item.preview || item.coreMeaning || item.notes || '暂无摘要', 110))}</p>
          ${state.query ? `<p class="match-note">匹配：${buildMatchSnippet([item.term, ...(item.aliases || []), item.coreMeaning, item.notes], state.query) || '当前卡片存在匹配'}</p>` : ''}
          <div class="term-footer">
            ${(item.relatedCases || [])
              .slice(0, 2)
              .map((caseItem) => `<a class="term-case-ref" href="${buildCaseHref(caseItem.id)}">${escapeHtml(caseItem.displayTitle)}</a>`)
              .join('')}
          </div>
          <div class="term-actions">
            <a class="detail-link" href="${buildTermHref(item.id)}">查看字词详情</a>
          </div>
        </article>
      `,
    )
    .join('');
}

function renderCaseResults(items) {
  if (!items.length) {
    browserList.innerHTML = '<article class="card"><h3>暂无符合条件的考据案例</h3><p>请更换问题片段、方法词或相关字词继续检索。</p></article>';
    return;
  }

  browserList.innerHTML = items
    .map(
      (item) => `
        <article class="card case-card browser-card">
          <div class="case-topline">
            <span class="case-term">${escapeHtml(item.termLabel || '关联字词')}</span>
            <div class="case-tags">
              <span class="tag">${escapeHtml(item.method || '未标注方法')}</span>
              <span class="tag muted">${escapeHtml(item.certainty || '未标注置信度')}</span>
            </div>
          </div>
          <h3>${escapeHtml(item.displayTitle || item.title)}</h3>
          ${item.displaySubtitle ? `<p class="case-subtitle">${escapeHtml(item.displaySubtitle)}</p>` : ''}
          <div class="case-members">
            ${(item.termNames || []).slice(0, 8).map((term) => `<span class="mini-chip">${escapeHtml(term)}</span>`).join('')}
          </div>
          <p class="case-summary">${escapeHtml(summarizeText(item.preview || item.conclusion || item.problem || '', 120))}</p>
          ${state.query ? `<p class="match-note">匹配：${buildMatchSnippet([item.displayTitle, item.displaySubtitle, item.termLabel, ...(item.termNames || []), item.problem, item.conclusion, ...(item.evidenceQuotes || [])], state.query) || '当前卡片存在匹配'}</p>` : ''}
          <div class="case-footer">
            <p><strong>证据数量</strong><span>${escapeHtml(String(item.evidenceCount || 0))} 条</span></p>
            <p><strong>状态</strong><span>${escapeHtml(item.status || '未标注')}</span></p>
          </div>
          <div class="case-actions">
            <a class="detail-link" href="${buildCaseHref(item.id)}">查看案例详情</a>
          </div>
        </article>
      `,
    )
    .join('');
}

function prepareSearchFromCurrentView() {
  if (state.view !== 'schema') {
    return;
  }

  state.view = 'terms';
  state.category = 'all';
  state.page = 1;
}

function applyPreset(trigger) {
  state.view = trigger.getAttribute('data-preset-view') || 'terms';
  state.mode = trigger.getAttribute('data-preset-mode') === 'fulltext' ? 'fulltext' : 'entry';
  state.query = trigger.getAttribute('data-preset-query') || '';
  state.category = trigger.getAttribute('data-preset-category') || 'all';
  state.page = 1;

  if (state.view === 'schema') {
    state.mode = 'entry';
    state.query = '';
    state.category = 'all';
  }
}

async function runBrowse() {
  renderSidebar();

  if (state.view === 'schema') {
    browserListSection.hidden = true;
    browserSchemaSection.hidden = false;
    if (browserPagination) {
      browserPagination.innerHTML = '';
      browserPagination.hidden = true;
    }
    browserHeading.textContent = '数据库结构';
    browserModeSelect.disabled = false;
    browserSearchInput.disabled = false;
    browserModeSelect.value = state.mode;
    browserSearchInput.value = state.query;
    if (browserSchemaSummary && state.bootstrap?.counts) {
      browserSchemaSummary.textContent = `展开数据库结构与统计（著作 ${state.bootstrap.counts.works || 0} / 词条 ${state.bootstrap.counts.terms || 0} / 案例 ${state.bootstrap.counts.cases || 0}）`;
    }
    renderSummary({ total: (state.bootstrap?.stores || []).length });
    renderStats(state.bootstrap?.counts || {});
    renderSchema(state.bootstrap?.stores || []);
    syncUrl();
    return;
  }

  browserModeSelect.disabled = false;
  browserSearchInput.disabled = false;
  browserModeSelect.value = state.mode;
  browserSearchInput.value = state.query;
  browserListSection.hidden = false;
  browserSchemaSection.hidden = true;
  browserHeading.textContent = state.view === 'cases' ? '考据案例数据库' : '字词数据库';

  const params = new URLSearchParams({
    view: state.view,
    category: state.category,
    mode: state.mode,
    q: state.query,
    page: String(state.page),
    pageSize: String(state.pageSize),
  });
  const result = await requestJson(`/api/browser?${params.toString()}`);
  state.page = Number(result.page || 1);

  renderSummary(result);
  renderPagination(result);
  if (state.view === 'cases') {
    renderCaseResults(result.items || []);
  } else {
    renderTermResults(result.items || []);
  }
  renderSidebar();
  syncUrl();
}

async function init() {
  loadUrlState();
  const bootstrap = await requestJson('/api/browser/bootstrap');
  state.bootstrap = bootstrap;
  renderHeroMeta();
  if (browserStatus) {
    browserStatus.textContent = `整理数据来源：${bootstrap.sourceLabel}`;
  }
  await runBrowse();
}

browserNav?.addEventListener('click', async (event) => {
  const trigger = event.target.closest('[data-view]');
  if (!trigger) return;

  state.view = trigger.getAttribute('data-view') || 'terms';
  state.category = 'all';
  state.page = 1;
  if (state.view === 'schema') {
    state.mode = 'entry';
    state.query = '';
  }
  renderSidebar();
  await runBrowse();
});

browserFilters?.addEventListener('click', async (event) => {
  const trigger = event.target.closest('[data-category]');
  if (!trigger) return;

  state.category = trigger.getAttribute('data-category') || 'all';
  state.page = 1;
  renderSidebar();
  await runBrowse();
});

browserSearchButton?.addEventListener('click', async () => {
  state.query = browserSearchInput?.value.trim() || '';
  state.mode = browserModeSelect?.value === 'fulltext' ? 'fulltext' : 'entry';
  state.page = 1;
  prepareSearchFromCurrentView();
  await runBrowse();
});

browserResetButton?.addEventListener('click', async () => {
  state.category = 'all';
  state.mode = 'entry';
  state.query = '';
  state.page = 1;
  renderSidebar();
  await runBrowse();
});

browserPresets?.addEventListener('click', async (event) => {
  const trigger = event.target.closest('[data-preset-view]');
  if (!trigger) return;

  applyPreset(trigger);
  if (browserSearchInput) {
    browserSearchInput.value = state.query;
  }
  if (browserModeSelect) {
    browserModeSelect.value = state.mode;
  }
  await runBrowse();
});

browserSummary?.addEventListener('click', async (event) => {
  const viewTrigger = event.target.closest('[data-summary-view]');
  if (viewTrigger) {
    state.view = viewTrigger.getAttribute('data-summary-view') || 'terms';
    state.category = 'all';
    state.page = 1;
    if (state.view === 'schema') {
      state.mode = 'entry';
      state.query = '';
    }
    await runBrowse();
    return;
  }

  const modeTrigger = event.target.closest('[data-summary-mode]');
  if (modeTrigger) {
    state.mode = modeTrigger.getAttribute('data-summary-mode') === 'fulltext' ? 'fulltext' : 'entry';
    browserModeSelect.value = state.mode;
    state.page = 1;
    await runBrowse();
    return;
  }

  const trigger = event.target.closest('[data-summary-action]');
  if (!trigger) return;

  const action = trigger.getAttribute('data-summary-action');
  if (action === 'result') {
    if (state.view === 'schema') {
      browserSchemaSection?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      browserListSection?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
});

browserPagination?.addEventListener('click', async (event) => {
  const pageButton = event.target.closest('[data-page]');
  if (pageButton) {
    state.page = Number(pageButton.getAttribute('data-page')) || 1;
    await runBrowse();
    return;
  }

  const actionButton = event.target.closest('[data-page-action]');
  if (!actionButton) return;

  const action = actionButton.getAttribute('data-page-action');
  if (action === 'prev' && state.page > 1) {
    state.page -= 1;
    await runBrowse();
    return;
  }

  if (action === 'next') {
    state.page += 1;
    await runBrowse();
  }
});

browserPagination?.addEventListener('submit', async (event) => {
  const form = event.target.closest('#browserPaginationForm');
  if (!form) return;

  event.preventDefault();
  const input = form.querySelector('#browserPageInput');
  const nextPage = Number(input?.value || 1);
  if (!Number.isFinite(nextPage) || nextPage < 1) {
    return;
  }

  state.page = Math.floor(nextPage);
  await runBrowse();
});

browserSearchInput?.addEventListener('keydown', async (event) => {
  if (event.key !== 'Enter') return;
  state.query = browserSearchInput?.value.trim() || '';
  state.mode = browserModeSelect?.value === 'fulltext' ? 'fulltext' : 'entry';
  state.page = 1;
  prepareSearchFromCurrentView();
  await runBrowse();
});

init().catch((error) => {
  if (browserStatus) {
    browserStatus.textContent = '数据库加载失败';
  }
  if (browserList) {
    browserList.innerHTML = '<article class="card"><h3>无法读取数据库</h3><p>请确认后端服务已启动，再刷新页面。</p></article>';
  }
  console.error(error);
});

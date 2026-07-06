const browserNav = document.querySelector('#browserNav');
const browserFilters = document.querySelector('#browserFilters');
const browserModeFilters = document.querySelector('#browserModeFilters');
const browserStatus = document.querySelector('#browserStatus');
const browserHeading = document.querySelector('#browserHeading');
const browserSearchInput = document.querySelector('#browserSearchInput');
const browserSearchButton = document.querySelector('#browserSearchButton');
const browserResetButton = document.querySelector('#browserResetButton');
const browserSummary = document.querySelector('#browserSummary');
const browserPresets = document.querySelector('#browserPresets');
const browserList = document.querySelector('#browserList');
const browserListSection = document.querySelector('#browserListSection');
const browserSchemaSection = document.querySelector('#browserSchemaSection');
const browserSchemaSummary = document.querySelector('#browserSchemaSummary');
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

  BrowserCommon.renderHeroItems(browserHeroMeta, items);
}

function renderSchema(stores) {
  BrowserCommon.renderSchemaCards(browserSchemaGrid, stores);
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
  BrowserCommon.renderChoiceButtons(browserNav, views, {
    activeValue: state.view,
    className: 'sidebar-button',
    emptyText: '暂无可用浏览类别。',
    valueAttribute: 'data-view',
  });

  const categories = getCurrentCategories();
  if (!categories.some((item) => item.value === state.category)) {
    state.category = 'all';
  }
  BrowserCommon.renderChoiceButtons(browserFilters, categories, {
    activeValue: state.category,
    className: 'filter-chip',
    emptyText: '当前分类为空。',
    valueAttribute: 'data-category',
  });

  BrowserCommon.renderChoiceButtons(browserModeFilters, [
    { value: 'entry', label: '条目检索' },
    { value: 'fulltext', label: '正文检索' },
  ], {
    activeValue: state.mode,
    className: 'filter-chip',
    valueAttribute: 'data-mode',
  });
}

function renderSummary(result) {
  if (!browserSummary) return;

  const categoryLabel = getCurrentCategories().find((item) => item.value === state.category)?.label || '全部';
  const modeLabel = state.mode === 'fulltext' ? '正文检索' : '条目检索';
  const viewLabel = (state.bootstrap?.views || []).find((item) => item.value === state.view)?.label || '字词库';

  browserSummary.innerHTML = `
    <div class="summary-row summary-row-meta">
      <span class="summary-pill muted">数据库：${escapeHtml(viewLabel)}</span>
      <span class="summary-pill muted">方法：${escapeHtml(categoryLabel)}</span>
      <span class="summary-pill muted">检索：${escapeHtml(modeLabel)}</span>
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
                <a class="detail-link detail-link-compact" href="${buildTermHref(item.id)}">查看详情</a>
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
              <a class="detail-link detail-link-compact" href="${buildCaseHref(item.id)}">查看详情</a>
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
    browserSearchInput.disabled = false;
    browserSearchInput.value = state.query;
    renderSummary({ total: (state.bootstrap?.stores || []).length });
    renderSchema(state.bootstrap?.stores || []);
    syncUrl();
    return;
  }

  browserSearchInput.disabled = false;
  browserSearchInput.value = state.query;
  browserListSection.hidden = false;
  browserSchemaSection.hidden = false;
  browserHeading.textContent = state.view === 'cases' ? '案例库' : '字词库';

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
    browserStatus.textContent = `数据库来源：${bootstrap.sourceLabel}`;
  }
  renderSchema(bootstrap.stores || []);
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

browserModeFilters?.addEventListener('click', async (event) => {
  const trigger = event.target.closest('[data-mode]');
  if (!trigger) return;

  state.mode = trigger.getAttribute('data-mode') === 'fulltext' ? 'fulltext' : 'entry';
  state.page = 1;
  renderSidebar();
  await runBrowse();
});

browserSearchButton?.addEventListener('click', async () => {
  state.query = browserSearchInput?.value.trim() || '';
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
  await runBrowse();
});

browserSummary?.addEventListener('click', async (event) => {
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

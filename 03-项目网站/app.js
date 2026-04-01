const list = document.querySelector('#caseList');
const caseList = list;
const termList = document.querySelector('#termList');
const searchInput = document.querySelector('#searchInput');
const clearSearch = document.querySelector('#clearSearch');
const searchQuick = document.querySelector('#searchQuick');
const dbStatus = document.querySelector('#dbStatus');
const dbStats = document.querySelector('#dbStats');
const schemaGrid = document.querySelector('#schemaGrid');
const searchSummary = document.querySelector('#searchSummary');
const heroTermCount = document.querySelector('#heroTermCount');
const heroCaseCount = document.querySelector('#heroCaseCount');
const heroEvidenceCount = document.querySelector('#heroEvidenceCount');
const heroFeatureTitle = document.querySelector('#heroFeatureTitle');
const heroFeatureMeta = document.querySelector('#heroFeatureMeta');
const heroFeatureLink = document.querySelector('#heroFeatureLink');

let searchTimer = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function buildTermHref(id) {
  return `./term.html?id=${encodeURIComponent(String(id))}`;
}

function buildCaseHref(id) {
  return `./case.html?id=${encodeURIComponent(String(id))}`;
}

function buildDatabaseHref(view, query = '') {
  const params = new URLSearchParams();
  params.set('view', view);
  if (query) {
    params.set('q', query);
    params.set('mode', 'fulltext');
  }
  return `./database.html?${params.toString()}`;
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

function splitItems(items, visibleCount) {
  return {
    visible: items.slice(0, visibleCount),
    hidden: items.slice(visibleCount),
  };
}

function renderQuickSearch(bootstrap) {
  if (!searchQuick) return;

  const fixedKeywords = ['始', '敬', '不我知', '通假', '因声求义', '义证'];
  const sampleKeywords = (bootstrap?.sampleTerms || [])
    .map((item) => item.term)
    .filter(Boolean)
    .slice(0, 6);
  const keywords = [...new Set([...fixedKeywords, ...sampleKeywords])].slice(0, 10);

  searchQuick.innerHTML = keywords
    .map((keyword) => `<button class="quick-chip" type="button" data-keyword="${escapeHtml(keyword)}">${escapeHtml(keyword)}</button>`)
    .join('');
}

function renderHeroShowcase(bootstrap) {
  if (heroTermCount) {
    heroTermCount.textContent = String(bootstrap.counts?.terms ?? 0);
  }
  if (heroCaseCount) {
    heroCaseCount.textContent = String(bootstrap.counts?.cases ?? 0);
  }
  if (heroEvidenceCount) {
    heroEvidenceCount.textContent = String(bootstrap.counts?.evidences ?? 0);
  }

  const featuredCase = bootstrap.featuredCases?.[0];
  if (!featuredCase) {
    return;
  }

  if (heroFeatureTitle) {
    heroFeatureTitle.textContent = featuredCase.displayTitle || featuredCase.title || '案例入口';
  }
  if (heroFeatureMeta) {
    heroFeatureMeta.textContent = [featuredCase.displaySubtitle, featuredCase.termLabel, `证据 ${featuredCase.evidenceCount || 0} 条`]
      .filter(Boolean)
      .join(' · ');
  }
  if (heroFeatureLink) {
    heroFeatureLink.setAttribute('href', buildCaseHref(featuredCase.id));
  }
}

function renderStats(counts) {
  if (!dbStats) return;

  const items = [
    { label: '著作', value: counts.works ?? 0 },
    { label: '片段', value: counts.passages ?? 0 },
    { label: '词条', value: counts.terms ?? 0 },
    { label: '案例', value: counts.cases ?? 0 },
    { label: '证据', value: counts.evidences ?? 0 },
  ];

  dbStats.innerHTML = items
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
  if (!schemaGrid) return;

  schemaGrid.innerHTML = '';
  stores.forEach((storeDefinition) => {
    const card = document.createElement('article');
    card.className = 'card';
    const keyMeta = storeDefinition.keyFields
      .map((field) => `<span class="tag muted">${escapeHtml(field)}</span>`)
      .join('');
    const indexMeta = storeDefinition.indexes
      .map((field) => `<span class="tag">idx:${escapeHtml(field)}</span>`)
      .join('');
    const fields = (storeDefinition.fields || [])
      .map(
        (field) => `
          <div class="field-row">
            <div class="field-name"><code>${escapeHtml(field.name)}</code></div>
            <div class="field-desc">${escapeHtml(field.description)}</div>
          </div>
        `,
      )
      .join('');

    card.innerHTML = `
      <h3>${escapeHtml(storeDefinition.label)}</h3>
      <p>${escapeHtml(storeDefinition.purpose)}</p>
      <div class="schema-meta">${keyMeta}${indexMeta}</div>
      <p class="db-status">当前记录：${storeDefinition.count} 条</p>
      <div class="field-list">${fields}</div>
    `;
    schemaGrid.appendChild(card);
  });
}

function renderSearchSummary(result) {
  if (!searchSummary) return;

  const query = String(result.query || '').trim();
  const termTotal = result.terms?.total ?? 0;
  const caseTotal = result.cases?.total ?? 0;
  const summary = query ? `检索“${escapeHtml(query)}”` : '默认预览';

  searchSummary.innerHTML = `
    <span class="summary-pill">${summary}</span>
    <span class="summary-pill muted">字词 ${escapeHtml(String(termTotal))}</span>
    <span class="summary-pill muted">案例 ${escapeHtml(String(caseTotal))}</span>
  `;
}

function renderTerms(result, query = '') {
  if (!termList) return;

  const items = result.items || [];
  termList.innerHTML = '';
  if (!items.length) {
    termList.innerHTML = '<article class="card"><h3>暂无匹配字词</h3><p>请更换单字、词语或义项继续检索。</p></article>';
    return;
  }

  const visibleCount = 5;
  const groups = splitItems(items, visibleCount);
  const renderTermCard = (item) => {
    const meta = [item.termType, item.category].filter(Boolean);
    const aliases = (item.aliases || [])
      .slice(0, 3)
      .map((alias) => `<span class="mini-chip">${escapeHtml(alias)}</span>`)
      .join('');
    const relatedCaseItems = (item.relatedCases || []).slice(0, 2);
    const relatedCases = relatedCaseItems
      .map(
        (caseItem) => `
          <a class="term-case-ref" href="${buildCaseHref(caseItem.id)}">
            ${escapeHtml(caseItem.displayTitle)}
          </a>
        `,
      )
      .join('');
    const extraCaseCount = Math.max((item.relatedCases || []).length - relatedCaseItems.length, 0);

    return `
      <article class="card term-card">
      <div class="term-card-top">
        <a class="term-glyph term-glyph-link" href="${buildTermHref(item.id)}">${escapeHtml(item.term || '未录入')}</a>
        <div class="term-meta-stack">
          <div class="case-tags">
            ${meta.map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join('') || '<span class="tag muted">未分类</span>'}
          </div>
          <p class="compact-note">关联案例 ${escapeHtml(String(item.caseCount || 0))} 条</p>
        </div>
      </div>
      <p class="term-core">${escapeHtml(summarizeText(item.coreMeaning || item.notes || '暂无释义摘要', 72))}</p>
      ${aliases ? `<div class="mini-chip-list">${aliases}</div>` : ''}
      ${relatedCases ? `<div class="term-footer">${relatedCases}</div>` : ''}
      ${extraCaseCount ? `<p class="compact-note">其余 ${escapeHtml(String(extraCaseCount))} 条案例请进入详情页查看。</p>` : ''}
      <div class="term-actions">
        <a class="detail-link" href="${buildTermHref(item.id)}">查看字词详情</a>
      </div>
      </article>
    `;
  };

  termList.innerHTML = groups.visible.map(renderTermCard).join('');

  const linkCard = document.createElement('article');
  linkCard.className = 'card result-link-card';
  linkCard.innerHTML = `
    <h3>阅读全部字词</h3>
    <p>当前区域固定展示 5 个字词入口，完整列表请进入数据库浏览页继续查看。</p>
    <a class="detail-link" href="${buildDatabaseHref('terms', query)}">进入字词浏览</a>
  `;
  termList.appendChild(linkCard);
}

function renderCases(result, query = '') {
  if (!caseList) return;

  const items = result.items || [];
  caseList.innerHTML = '';
  if (!items.length) {
    caseList.innerHTML = '<article class="card"><h3>暂无相关案例</h3><p>当前关键词没有匹配到可展示的考释案例。</p></article>';
    return;
  }

  const visibleCount = 5;
  const groups = splitItems(items, visibleCount);
  const renderCaseCard = (item) => {
    const visibleTerms = (item.termNames || []).slice(0, 6);
    const extraTerms = Math.max((item.termNames || []).length - visibleTerms.length, 0);
    const termMembers = visibleTerms
      .map((term) => `<span class="mini-chip">${escapeHtml(term)}</span>`)
      .join('');
    const evidencePreview = (item.evidenceQuotes || [])
      .slice(0, 1)
      .map((quote) => `<span class="quote-chip">${escapeHtml(quote)}</span>`)
      .join('');
    const summaryText = summarizeText(item.conclusion || item.problem || item.processText || '暂无摘要', 96);

    return `
      <article class="card case-card">
      <div class="case-topline">
        <span class="case-term">${escapeHtml(item.termLabel || item.termName || '未单独关联')}</span>
        <div class="case-tags">
          <span class="tag">${escapeHtml(item.method || '未标注方法')}</span>
          <span class="tag muted">${escapeHtml(item.certainty || '未标注置信度')}</span>
        </div>
      </div>
      <h3>${escapeHtml(item.displayTitle || item.title || '未命名案例')}</h3>
      ${item.displaySubtitle ? `<p class="case-subtitle">${escapeHtml(item.displaySubtitle)}</p>` : ''}
      ${termMembers ? `<div class="case-members">${termMembers}</div>` : ''}
      ${extraTerms ? `<p class="compact-note">另有 ${escapeHtml(String(extraTerms))} 个相关字词，进入详情页展开。</p>` : ''}
      <p class="case-summary">${escapeHtml(summaryText)}</p>
      <div class="case-meta">
        <p><strong>二王出处</strong><span>${escapeHtml(item.erwangWorkTitle || '未录入')}${item.erwangLocation ? ` · ${escapeHtml(item.erwangLocation)}` : ''}</span></p>
        <p><strong>原始文本</strong><span>${escapeHtml(item.targetWorkTitle || '暂未关联原始经典')}${item.targetLocation ? ` · ${escapeHtml(item.targetLocation)}` : ''}</span></p>
      </div>
      <div class="case-footer">
        <p><strong>证据数量</strong><span>${escapeHtml(String(item.evidenceCount || 0))} 条</span></p>
        <p><strong>状态</strong><span>${escapeHtml(item.status || '未标注')}</span></p>
      </div>
      ${evidencePreview ? `<div class="quote-list">${evidencePreview}</div>` : ''}
      <div class="case-actions">
        <a class="detail-link" href="${buildCaseHref(item.id)}">查看案例详情</a>
      </div>
      </article>
    `;
  };

  caseList.innerHTML = groups.visible.map(renderCaseCard).join('');

  const linkCard = document.createElement('article');
  linkCard.className = 'card result-link-card';
  linkCard.innerHTML = `
    <h3>阅读全部案例</h3>
    <p>当前区域固定展示 5 个案例预览，完整列表请进入数据库浏览页继续阅读。</p>
    <a class="detail-link" href="${buildDatabaseHref('cases', query)}">进入案例浏览</a>
  `;
  caseList.appendChild(linkCard);
}

async function loadBootstrap() {
  if (dbStatus) {
    dbStatus.textContent = '数据库状态：连接中...';
  }
  const bootstrap = await requestJson('/api/bootstrap');
  renderStats(bootstrap.counts);
  renderSchema(bootstrap.stores);
  renderQuickSearch(bootstrap);
  renderHeroShowcase(bootstrap);
  if (dbStatus) {
    dbStatus.textContent = `数据库状态：已连接 · ${bootstrap.sourceLabel}（${bootstrap.totalRecords} 条总记录）`;
  }
  if (searchInput) {
    searchInput.placeholder = `输入字词、方法词或片段：如 始 / 犹豫 / 不我知（当前词条 ${bootstrap.counts.terms} 条）`;
  }
}

async function searchContent(query) {
  const data = await requestJson(`/api/search?q=${encodeURIComponent(query)}`);
  renderSearchSummary(data);
  renderTerms(data.terms || {}, data.query || '');
  renderCases(data.cases || {}, data.query || '');
}

async function init() {
  try {
    await loadBootstrap();
    await searchContent('');
  } catch (error) {
    if (dbStatus) {
      dbStatus.textContent = '数据库状态：连接失败，请先运行本地服务';
    }
    if (dbStats) {
      dbStats.innerHTML = '';
    }
    if (schemaGrid) {
      schemaGrid.innerHTML = '<article class="card"><h3>无法加载数据库</h3><p>请使用 <code>npm start</code> 启动根目录服务后再访问。</p></article>';
    }
    if (searchSummary) {
      searchSummary.innerHTML = '';
    }
    if (termList) {
      termList.innerHTML = '<article class="card"><h3>暂无字词数据</h3><p>后端 API 未启动，前端无法加载字词入口。</p></article>';
    }
    if (caseList) {
      caseList.innerHTML = '<article class="card"><h3>暂无案例数据</h3><p>后端 API 未启动，前端无法读取案例结果。</p></article>';
    }
    console.error(error);
  }
}

if (searchInput) {
  searchInput.addEventListener('input', (event) => {
    clearTimeout(searchTimer);
    const query = event.target.value;
    searchTimer = setTimeout(() => {
      searchContent(query).catch((error) => {
        if (dbStatus) {
          dbStatus.textContent = '数据库状态：搜索失败';
        }
        console.error(error);
      });
    }, 180);
  });
}

if (clearSearch) {
  clearSearch.addEventListener('click', () => {
    if (searchInput) {
      searchInput.value = '';
      searchContent('').catch((error) => {
        console.error(error);
      });
    }
  });
}

if (searchQuick) {
  searchQuick.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-keyword]');
    if (!trigger) {
      return;
    }

    const keyword = trigger.getAttribute('data-keyword') || '';
    if (searchInput) {
      searchInput.value = keyword;
    }
    searchContent(keyword).catch((error) => {
      console.error(error);
    });
  });
}

init();

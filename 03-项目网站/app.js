const list = document.querySelector('#caseList');
const caseList = list;
const termList = document.querySelector('#termList');
const searchInput = document.querySelector('#searchInput');
const dbStatus = document.querySelector('#dbStatus');
const dbStats = document.querySelector('#dbStats');
const schemaGrid = document.querySelector('#schemaGrid');
const searchSummary = document.querySelector('#searchSummary');

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

async function requestJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
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
  const summary = query
    ? `当前检索 “${escapeHtml(query)}” ，命中 ${escapeHtml(String(termTotal))} 个字词、${escapeHtml(String(caseTotal))} 个相关案例。`
    : `当前展示高频字词入口与对应案例，共预览 ${escapeHtml(String(termTotal))} 个字词、${escapeHtml(String(caseTotal))} 个案例。`;

  searchSummary.innerHTML = `
    <article class="card">
      <h3>检索说明</h3>
      <p>${summary}</p>
    </article>
  `;
}

function renderTerms(result) {
  if (!termList) return;

  const items = result.items || [];
  termList.innerHTML = '';
  if (!items.length) {
    termList.innerHTML = '<article class="card"><h3>暂无匹配字词</h3><p>请更换单字、词语或义项继续检索。</p></article>';
    return;
  }

  items.forEach((item) => {
    const meta = [item.termType, item.category].filter(Boolean);
    const aliases = (item.aliases || [])
      .slice(0, 6)
      .map((alias) => `<span class="mini-chip">${escapeHtml(alias)}</span>`)
      .join('');
    const relatedCases = (item.relatedCases || [])
      .map(
        (caseItem) => `
          <a class="term-case-ref" href="${buildCaseHref(caseItem.id)}">
            ${escapeHtml(caseItem.displayTitle)}
          </a>
        `,
      )
      .join('');

    const card = document.createElement('article');
    card.className = 'card term-card';
    card.innerHTML = `
      <div class="term-card-top">
        <a class="term-glyph term-glyph-link" href="${buildTermHref(item.id)}">${escapeHtml(item.term || '未录入')}</a>
        <div class="term-meta-stack">
          <div class="case-tags">
            ${meta.map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join('') || '<span class="tag muted">未分类</span>'}
          </div>
          <p class="compact-note">关联案例 ${escapeHtml(String(item.caseCount || 0))} 条</p>
        </div>
      </div>
      <p class="term-core">${escapeHtml(item.coreMeaning || item.notes || '暂无释义摘要')}</p>
      ${aliases ? `<div class="mini-chip-list">${aliases}</div>` : ''}
      ${relatedCases ? `<div class="term-footer">${relatedCases}</div>` : ''}
      <div class="term-actions">
        <a class="detail-link" href="${buildTermHref(item.id)}">查看字词详情</a>
      </div>
    `;
    termList.appendChild(card);
  });

  if (result.truncated) {
    const notice = document.createElement('article');
    notice.className = 'card';
    notice.innerHTML = `
      <h3>字词结果已截断</h3>
      <p>当前命中 ${escapeHtml(String(result.total))} 条，仅展示前 ${escapeHtml(String(result.limit))} 条以保持首页清晰。</p>
    `;
    termList.appendChild(notice);
  }
}

function renderCases(result) {
  if (!caseList) return;

  const items = result.items || [];
  caseList.innerHTML = '';
  if (!items.length) {
    caseList.innerHTML = '<article class="card"><h3>暂无相关案例</h3><p>当前关键词没有匹配到可展示的考释案例。</p></article>';
    return;
  }

  items.forEach((item) => {
    const termMembers = (item.termNames || [])
      .map((term) => `<span class="mini-chip">${escapeHtml(term)}</span>`)
      .join('');
    const evidencePreview = (item.evidenceQuotes || [])
      .slice(0, 2)
      .map((quote) => `<span class="quote-chip">${escapeHtml(quote)}</span>`)
      .join('');
    const card = document.createElement('article');
    card.className = 'card case-card';
    card.innerHTML = `
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
      <div class="case-meta">
        <p><strong>二王出处</strong><span>${escapeHtml(item.erwangWorkTitle || '未录入')}${item.erwangLocation ? ` · ${escapeHtml(item.erwangLocation)}` : ''}</span></p>
        <p><strong>原始文本</strong><span>${escapeHtml(item.targetWorkTitle || '暂未关联原始经典')}${item.targetLocation ? ` · ${escapeHtml(item.targetLocation)}` : ''}</span></p>
      </div>
      <div class="case-body">
        <p><strong>问题</strong><span>${escapeHtml(item.problem || '暂无问题描述')}</span></p>
        <p><strong>过程</strong><span>${escapeHtml(item.processText || '暂无过程摘要')}</span></p>
        <p><strong>结论</strong><span>${escapeHtml(item.conclusion || '暂无结论')}</span></p>
      </div>
      <div class="case-footer">
        <p><strong>证据数量</strong><span>${escapeHtml(String(item.evidenceCount || 0))} 条</span></p>
        <p><strong>状态</strong><span>${escapeHtml(item.status || '未标注')}</span></p>
      </div>
      ${evidencePreview ? `<div class="quote-list">${evidencePreview}</div>` : ''}
      <div class="case-actions">
        <a class="detail-link" href="${buildCaseHref(item.id)}">查看案例详情</a>
      </div>
    `;
    caseList.appendChild(card);
  });

  if (result.truncated) {
    const notice = document.createElement('article');
    notice.className = 'card';
    notice.innerHTML = `
      <h3>案例结果已截断</h3>
      <p>当前检索命中 ${escapeHtml(String(result.total))} 条，仅展示前 ${escapeHtml(String(result.limit))} 条以保证首页可读性。</p>
    `;
    caseList.appendChild(notice);
  }
}

async function loadBootstrap() {
  if (dbStatus) {
    dbStatus.textContent = '数据库状态：连接中...';
  }
  const bootstrap = await requestJson('/api/bootstrap');
  renderStats(bootstrap.counts);
  renderSchema(bootstrap.stores);
  if (dbStatus) {
    dbStatus.textContent = `数据库状态：已连接 · ${bootstrap.sourceLabel}（${bootstrap.totalRecords} 条总记录）`;
  }
  if (searchInput) {
    searchInput.placeholder = `输入单字、词语或义项：如 始 / 犹豫 / 不我知（当前词条 ${bootstrap.counts.terms} 条）`;
  }
}

async function searchContent(query) {
  const data = await requestJson(`/api/search?q=${encodeURIComponent(query)}`);
  renderSearchSummary(data);
  renderTerms(data.terms || {});
  renderCases(data.cases || {});
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

init();

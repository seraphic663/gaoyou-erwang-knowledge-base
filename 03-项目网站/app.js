const list = document.querySelector('#caseList');
const searchInput = document.querySelector('#searchInput');
const dbStatus = document.querySelector('#dbStatus');
const dbStats = document.querySelector('#dbStats');
const schemaGrid = document.querySelector('#schemaGrid');

let searchTimer = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
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

function renderCases(items) {
  if (!list) return;

  list.innerHTML = '';
  if (!items.length) {
    list.innerHTML = '<article class="card"><h3>暂无结果</h3><p>请更换关键词继续检索。</p></article>';
    return;
  }

  items.forEach((item) => {
    const evidencePreview = (item.evidenceQuotes || [])
      .slice(0, 2)
      .map((quote) => `<span class="quote-chip">${escapeHtml(quote)}</span>`)
      .join('');
    const card = document.createElement('article');
    card.className = 'card case-card';
    card.innerHTML = `
      <div class="case-topline">
        <span class="case-term">${escapeHtml(item.termName || '未单独关联')}</span>
        <div class="case-tags">
          <span class="tag">${escapeHtml(item.method)}</span>
          <span class="tag muted">${escapeHtml(item.certainty)}</span>
        </div>
      </div>
      <h3>${escapeHtml(item.title)}</h3>
      <div class="case-meta">
        <p><strong>二王出处</strong><span>${escapeHtml(item.erwangWorkTitle || '未录入')}${item.erwangLocation ? ` · ${escapeHtml(item.erwangLocation)}` : ''}</span></p>
        <p><strong>原始文本</strong><span>${escapeHtml(item.targetWorkTitle || '暂未关联原始经典')}${item.targetLocation ? ` · ${escapeHtml(item.targetLocation)}` : ''}</span></p>
      </div>
      <div class="case-body">
        <p><strong>问题</strong><span>${escapeHtml(item.problem)}</span></p>
        <p><strong>过程</strong><span>${escapeHtml(item.processText)}</span></p>
        <p><strong>结论</strong><span>${escapeHtml(item.conclusion)}</span></p>
      </div>
      <div class="case-footer">
        <p><strong>证据数量</strong><span>${escapeHtml(String(item.evidenceCount))} 条</span></p>
        <p><strong>状态</strong><span>${escapeHtml(item.status)}</span></p>
      </div>
      ${evidencePreview ? `<div class="quote-list">${evidencePreview}</div>` : ''}
    `;
    list.appendChild(card);
  });
}

async function loadBootstrap() {
  if (dbStatus) {
    dbStatus.textContent = '数据库状态：连接中...';
  }
  const bootstrap = await requestJson('/api/bootstrap');
  renderStats(bootstrap.counts);
  renderSchema(bootstrap.stores);
  if (dbStatus) {
    dbStatus.textContent = `数据库状态：已连接（${bootstrap.totalRecords} 条总记录）`;
  }
  if (searchInput) {
    searchInput.placeholder = `输入关键词：如 犹豫 / 不我知 / 术字乐甫（当前词条 ${bootstrap.sampleTerms.length} 条）`;
  }
}

async function searchCases(query) {
  const data = await requestJson(`/api/cases?q=${encodeURIComponent(query)}`);
  renderCases(data.items || []);
}

async function init() {
  try {
    await loadBootstrap();
    await searchCases('');
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
    if (list) {
      list.innerHTML = '<article class="card"><h3>暂无数据</h3><p>后端 API 未启动，前端无法读取 demo 数据库。</p></article>';
    }
    console.error(error);
  }
}

if (searchInput) {
  searchInput.addEventListener('input', (event) => {
    clearTimeout(searchTimer);
    const query = event.target.value;
    searchTimer = setTimeout(() => {
      searchCases(query).catch((error) => {
        if (dbStatus) {
          dbStatus.textContent = '数据库状态：搜索失败';
        }
        console.error(error);
      });
    }, 180);
  });
}

init();

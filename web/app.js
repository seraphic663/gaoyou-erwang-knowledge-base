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
  const items = [
    { label: '文献', value: counts.works ?? 0 },
    { label: '段落', value: counts.passages ?? 0 },
    { label: '词条', value: counts.terms ?? 0 },
    { label: '案例', value: counts.cases ?? 0 },
    { label: '证据', value: counts.evidences ?? 0 },
    { label: '关系', value: counts.relations ?? 0 },
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

    card.innerHTML = `
      <h3>${escapeHtml(storeDefinition.label)}</h3>
      <p>${escapeHtml(storeDefinition.purpose)}</p>
      <div class="schema-meta">${keyMeta}${indexMeta}</div>
      <p class="db-status">当前记录：${storeDefinition.count} 条</p>
    `;
    schemaGrid.appendChild(card);
  });
}

function renderCases(items) {
  list.innerHTML = '';
  if (!items.length) {
    list.innerHTML = '<article class="card"><h3>暂无结果</h3><p>请更换关键词继续检索。</p></article>';
    return;
  }

  items.forEach((item) => {
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = `
      <h3>${escapeHtml(item.title)}</h3>
      <p><strong>原始出处：</strong>${escapeHtml(item.workTitle)} · ${escapeHtml(item.termName)}</p>
      <p><strong>问题：</strong>${escapeHtml(item.problem)}</p>
      <p><strong>方法：</strong>${escapeHtml(item.method)}</p>
      <p><strong>步骤：</strong>${escapeHtml(item.steps.join(' → '))}</p>
      <p><strong>证据：</strong>${escapeHtml(String(item.evidenceCount))} 条</p>
      <p><strong>结论：</strong>${escapeHtml(item.conclusion)}</p>
      <p><strong>状态：</strong>${escapeHtml(item.status)}</p>
    `;
    list.appendChild(card);
  });
}

async function loadBootstrap() {
  dbStatus.textContent = '数据库状态：连接中...';
  const bootstrap = await requestJson('/api/bootstrap');
  renderStats(bootstrap.counts);
  renderSchema(bootstrap.stores);
  dbStatus.textContent = `数据库状态：已连接（${bootstrap.totalRecords} 条总记录）`;
  searchInput.placeholder = `输入关键词：如 犹豫 / 能不我知 / 术（当前词条 ${bootstrap.sampleTerms.length} 条）`;
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
    dbStatus.textContent = '数据库状态：连接失败，请先运行本地服务';
    dbStats.innerHTML = '';
    schemaGrid.innerHTML = '<article class="card"><h3>无法加载数据库</h3><p>请使用 <code>npm start</code> 启动根目录服务后再访问。</p></article>';
    list.innerHTML = '<article class="card"><h3>暂无数据</h3><p>后端 API 未启动，前端无法读取 demo 数据库。</p></article>';
    console.error(error);
  }
}

searchInput.addEventListener('input', (event) => {
  clearTimeout(searchTimer);
  const query = event.target.value;
  searchTimer = setTimeout(() => {
    searchCases(query).catch((error) => {
      dbStatus.textContent = '数据库状态：搜索失败';
      console.error(error);
    });
  }, 180);
});

init();

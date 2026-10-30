const caseList = document.querySelector('#caseList');
const termList = document.querySelector('#termList');
const searchInput = document.querySelector('#searchInput');
const clearSearch = document.querySelector('#clearSearch');
const searchQuick = document.querySelector('#searchQuick');
const dbStatus = document.querySelector('#dbStatus');
const dbStats = document.querySelector('#dbStats');
const searchSummary = document.querySelector('#searchSummary');

let searchTimer = null;
let currentSearchId = 0;
let searchController = null;

const relationLabels = {
  gloss: '训释',
  loan: '通假',
  reading: '读法',
  emendation: '校勘',
  emendation_phrase: '短语校勘',
};

function relationLabel(item) {
  return relationLabels[item.relation_type] || String(item.relation_label || '').replace(/候[选選]/g, '') || item.relation_type || '关系类型未标明';
}

function relationArrow(item) {
  return item.directionality === 'symmetric' ? '↔' : '→';
}

function relationFormMarkup(value, side) {
  if (value === null || value === undefined) return `<span>${escapeHtml(`（${side}端未提供）`)}</span>`;
  const isEmptyForm = String(value) === '';
  return isEmptyForm
    ? '<span title="此处无字" aria-label="此处无字">∅</span>'
    : `<span>${escapeHtml(value)}</span>`;
}

function querySideLabel(item) {
  if (item.directionality === 'symmetric') return '双向关系命中';
  return ({ left: '原词／原句命中', right: '释义／异文命中', both: '两端命中' })[item.query_side] || '';
}

function relationCues(item) {
  const raw = item.relation_cues || item.cues || item.relation_cue || item.cue
    || (Array.isArray(item.claim_cues) ? item.claim_cues.map((claim) => claim.relation_cue) : []);
  const cues = Array.isArray(raw) ? raw : [raw];
  return [...new Set(cues.map((cue) => String(typeof cue === 'object' ? cue?.relation_cue || cue?.cue || '' : cue || '').trim()).filter(Boolean))];
}

function machineAnchorId(prefix, value) {
  const encoded = Array.from(String(value ?? '')).map((character) => {
    return /^[a-zA-Z0-9_-]$/.test(character)
      ? character
      : `_u${character.codePointAt(0).toString(16)}_`;
  }).join('');
  return `${prefix}-${encoded || 'item'}`;
}

function buildDatabaseHref(view, query = '', anchor = '') {
  const params = new URLSearchParams();
  if (String(query || '').trim()) params.set('q', String(query).trim());
  params.set('view', view);
  params.set('match', 'all');
  params.set('page', '1');
  const path = view === 'cases' ? '/cases' : '/terms';
  return `${path}?${params.toString()}${anchor ? `#${anchor}` : ''}`;
}

function formatCount(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '0';
}

function renderQuickSearch() {
  if (!searchQuick) return;
  const keywords = ['農', '毋', '無', '反', '不', '努力', '農力'];
  searchQuick.innerHTML = keywords
    .map((keyword) => `<button class="quick-chip" type="button" data-keyword="${escapeHtml(keyword)}">${escapeHtml(keyword)}</button>`)
    .join('');
}

function renderStats(meta) {
  if (!dbStats) return;
  const counts = meta.counts || {};
  const items = [
    { label: '二王原典', value: meta.works?.length ?? 4 },
    { label: '原典原文段', value: counts.source_passages },
    { label: '机器字词关系 · 待核', value: counts.active_relation_groups },
    { label: '机器校读点候选 · 待核', value: counts.active_proofreading_points },
    { label: '机器关系主张 · 待核', value: counts.active_claims },
  ];
  dbStats.innerHTML = items.map((item) => `
    <div class="stat-card">
      <div class="value">${escapeHtml(formatCount(item.value))}</div>
      <div class="label">${escapeHtml(item.label)}</div>
    </div>
  `).join('');
}

function renderSearchSummary(termResult, caseResult, query) {
  if (!searchSummary) return;
  const normalizedQuery = String(query || '').trim();
  const matchedClaims = termResult.matched_claim_count ?? termResult.matched_claim_ids?.length ?? 0;
  const relationGroups = termResult.relation_group_count ?? termResult.total ?? 0;
  const caseCount = caseResult.case_count ?? caseResult.total ?? 0;
  const heading = normalizedQuery ? `检索“${escapeHtml(normalizedQuery)}”` : '机器候选预览';
  searchSummary.innerHTML = `
    <span class="summary-pill">${heading} · 关系主张 ${escapeHtml(String(matchedClaims))} · 字词组 ${escapeHtml(String(relationGroups))} · 校读点 ${escapeHtml(String(caseCount))}</span>
  `;
}

function renderTermCard(item, index, query) {
  const claimIds = Array.isArray(item.claim_ids) ? item.claim_ids : [];
  const stableKey = item.id || claimIds[0] || `${item.left_form || ''}-${item.right_form || ''}-${index}`;
  const anchor = machineAnchorId('ml-relation-card', stableKey);
  const cases = Array.isArray(item.cases) ? item.cases : [];
  const support = cases[0];
  const cues = relationCues(item);
  const side = querySideLabel(item);
  const caseMarkup = support ? `
    <div class="term-footer">
      <span>${escapeHtml(support.work_title || support.work_key || '二王原典')}${support.location ? ` · ${escapeHtml(support.location)}` : ''}</span>
      ${support.quote ? `<blockquote class="quote-chip">${escapeHtml(summarizeText(support.quote, 180))}</blockquote>` : ''}
    </div>
  ` : '';

  return `
    <article class="card term-card">
      <div class="case-tags">
        <span class="tag">机器候选 · 待核</span>
        <span class="tag muted">${escapeHtml(relationLabel(item))}</span>
      </div>
      <h3 class="term-core">${relationFormMarkup(item.left_form, '左')} <span aria-label="${item.directionality === 'symmetric' ? '对称关系' : '原文叙述方向'}">${relationArrow(item)}</span> ${relationFormMarkup(item.right_form, '右')}</h3>
      <p class="compact-note">${side ? `${escapeHtml(side)} · ` : ''}${escapeHtml(String(claimIds.length))} 条命中关系主张 · ${escapeHtml(String(cases.length))} 个关联案例</p>
      ${cues.length ? `<p class="match-note">原文关系措辞：${cues.map(escapeHtml).join('、')}</p>` : ''}
      ${caseMarkup}
      <div class="term-actions">
        <a class="detail-link" href="${buildDatabaseHref('terms', query, anchor)}">在字词视图中打开</a>
      </div>
    </article>
  `;
}

function renderTerms(result, query = '') {
  if (!termList) return;
  const items = Array.isArray(result.items) ? result.items.slice(0, 3) : [];
  if (!items.length) {
    termList.innerHTML = '<article class="card"><h3>暂无关系字词</h3><p>可换一个字词或短语继续检索。</p></article>';
    return;
  }
  termList.innerHTML = items.map((item, index) => renderTermCard(item, index, query)).join('');

  const linkCard = document.createElement('article');
  linkCard.className = 'card result-link-card';
  linkCard.innerHTML = `
    <h3>查看全部字词关系</h3>
    <p>进入按字词分组的机器结果。</p>
    <a class="detail-link" href="${buildDatabaseHref('terms', query)}">打开字词视图</a>
  `;
  termList.appendChild(linkCard);
}

function renderCaseCard(item, index, query) {
  const stableKey = item.id || item.passage_id || `case-${index + 1}`;
  const anchor = machineAnchorId('ml-case-card', stableKey);
  const relations = (Array.isArray(item.relations) ? item.relations : []).slice(0, 2);
  const relationMarkup = relations.map((relation) => `
    <p class="compact-note"><span class="tag muted">${escapeHtml(relationLabel(relation))}</span>
      ${relationFormMarkup(relation.left_form, '左')} ${relationArrow(relation)} ${relationFormMarkup(relation.right_form, '右')}
      ${relationCues(relation).length ? `· ${relationCues(relation).map(escapeHtml).join('、')}` : ''}
    </p>
  `).join('');
  const title = item.work_title || item.work_key || '二王原典';

  return `
    <article class="card case-card">
      <div class="case-tags"><span class="tag">机器候选 · 待核</span></div>
      <h3>${escapeHtml(title)}</h3>
      <p class="case-subtitle">${escapeHtml(item.location || item.passage_id || '位置未注明')}</p>
      ${item.quote ? `<blockquote class="case-summary">${escapeHtml(summarizeText(item.quote, 180))}</blockquote>` : ''}
      ${relationMarkup}
      <div class="case-actions">
        <a class="detail-link" href="${buildDatabaseHref('cases', query, anchor)}">在案例视图中打开</a>
      </div>
    </article>
  `;
}

function renderCases(result, query = '') {
  if (!caseList) return;
  const items = Array.isArray(result.items) ? result.items.slice(0, 3) : [];
  if (!items.length) {
    caseList.innerHTML = '<article class="card"><h3>暂无对应校读点</h3><p>当前查询没有匹配到机器案例。</p></article>';
    return;
  }
  caseList.innerHTML = items.map((item, index) => renderCaseCard(item, index, query)).join('');

  const linkCard = document.createElement('article');
  linkCard.className = 'card result-link-card';
  linkCard.innerHTML = `
    <h3>查看全部案例</h3>
    <p>进入按校读点分组的机器结果。</p>
    <a class="detail-link" href="${buildDatabaseHref('cases', query)}">打开案例视图</a>
  `;
  caseList.appendChild(linkCard);
}

function sameClaimSet(left, right) {
  const leftIds = [...new Set(left.matched_claim_ids || [])].map(String).sort();
  const rightIds = [...new Set(right.matched_claim_ids || [])].map(String).sort();
  return leftIds.length === rightIds.length && leftIds.every((id, index) => id === rightIds[index]);
}

function machineSearchUrl(query, view) {
  const params = new URLSearchParams();
  params.set('q', query);
  params.set('view', view);
  params.set('match', 'all');
  params.set('page', '1');
  params.set('page_size', '10');
  params.set('include_mentions', '0');
  return `/api/machine/search?${params.toString()}`;
}

async function searchContent(query) {
  const normalizedQuery = String(query || '').normalize('NFKC').trim();
  searchController?.abort();
  const controller = new AbortController();
  searchController = controller;
  const requestId = ++currentSearchId;
  if (searchSummary) searchSummary.textContent = '正在检索机器关系……';

  try {
    const [termResult, caseResult] = await Promise.all([
      requestJson(machineSearchUrl(normalizedQuery, 'terms'), { signal: controller.signal }),
      requestJson(machineSearchUrl(normalizedQuery, 'cases'), { signal: controller.signal }),
    ]);
    if (requestId !== currentSearchId) return;
    if (termResult.available === false || caseResult.available === false) throw new Error('机器库暂不可用');
    if (termResult.run?.id !== caseResult.run?.id || !sameClaimSet(termResult, caseResult)) {
      throw new Error('字词与案例视图未返回同一批关系命中');
    }
    renderSearchSummary(termResult, caseResult, normalizedQuery);
    renderTerms(termResult, normalizedQuery);
    renderCases(caseResult, normalizedQuery);
  } catch (error) {
    if (requestId !== currentSearchId || error?.name === 'AbortError') return;
    if (searchSummary) searchSummary.textContent = error.message === '字词与案例视图未返回同一批关系命中'
      ? '字词与案例视图暂不同步，请稍后重试。'
      : '机器关系暂不可用。';
    if (termList) termList.innerHTML = '<article class="card"><h3>暂时无法读取机器结果</h3></article>';
    if (caseList) caseList.innerHTML = '<article class="card"><h3>暂时无法读取机器结果</h3></article>';
  }
}

async function loadMachineMeta() {
  if (dbStatus) dbStatus.textContent = '机器库状态：连接中……';
  try {
    const meta = await requestJson('/api/machine/meta');
    if (meta.available === false) throw new Error('unavailable');
    renderStats(meta);
    renderQuickSearch();
    if (dbStatus) dbStatus.textContent = `机器库已连接 · ${meta.works?.length ?? 4} 部二王原典 · 机器候选待核`;
  } catch {
    if (dbStatus) dbStatus.textContent = '机器库暂不可用。';
    if (dbStats) dbStats.innerHTML = '';
    renderQuickSearch();
  }
}

function scheduleSearch(query) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => searchContent(query), 300);
}

loadMachineMeta();
searchContent(searchInput?.value || '');

if (searchInput) {
  searchInput.placeholder = '输入字词或短语，如：農、毋 無';
  searchInput.addEventListener('input', (event) => scheduleSearch(event.target.value));
}

if (clearSearch) {
  clearSearch.addEventListener('click', () => {
    clearTimeout(searchTimer);
    if (searchInput) searchInput.value = '';
    searchContent('');
  });
}

if (searchQuick) {
  searchQuick.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-keyword]');
    if (!trigger) return;
    clearTimeout(searchTimer);
    const keyword = trigger.getAttribute('data-keyword') || '';
    if (searchInput) searchInput.value = keyword;
    searchContent(keyword);
  });
}

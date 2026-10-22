const detailTitle = document.querySelector('#detailTitle');
const detailLead = document.querySelector('#detailLead');
const detailMain = document.querySelector('#detailMain');

function getRequiredId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('id') || '';
}

function renderDetailNotFound(message) {
  if (detailMain) {
    detailMain.innerHTML = `
      <article class="card">
        <h3>未找到对应记录</h3>
        <p>${escapeHtml(message)}</p>
      </article>
    `;
  }
}

function renderTermDetail(payload) {
  if (detailTitle) {
    detailTitle.textContent = payload.term || '未命名字词';
  }
  if (detailLead) {
    detailLead.textContent = summarizeText(payload.coreMeaning || payload.notes || '当前字词暂无摘要说明。', 150);
  }
  const aliasList = (payload.aliases || [])
    .map((alias) => `<span class="mini-chip">${escapeHtml(alias)}</span>`)
    .join('');
  const evidenceTypeList = (payload.evidenceTypes || [])
    .map((type) => `<span class="tag">${escapeHtml(type)}</span>`)
    .join('');
  const relatedWorks = (payload.relatedWorks || [])
    .map((work) => `<span class="term-case-ref">${escapeHtml(work)}</span>`)
    .join('');
  const relatedCaseCards = (payload.relatedCases || [])
    .map(
      (item) => `
        <article class="card detail-card">
          <div class="case-topline">
            <span class="case-term">${escapeHtml(item.termLabel || item.termName || '关联案例')}</span>
            <div class="case-tags">
              <span class="tag">${escapeHtml(item.method || '未标注方法')}</span>
              <span class="tag muted">${escapeHtml(item.certainty || '未标注置信度')}</span>
            </div>
          </div>
          <h3>${escapeHtml(item.displayTitle || item.title)}</h3>
          ${item.displaySubtitle ? `<p class="case-subtitle">${escapeHtml(item.displaySubtitle)}</p>` : ''}
          <p class="detail-paragraph">${escapeHtml(item.conclusion || item.problem || '暂无摘要')}</p>
          <a class="detail-link" href="${buildCaseHref(item.id)}">进入案例详情</a>
        </article>
      `,
    );
  const relatedCaseGroups = splitItems(relatedCaseCards, 4);
  const evidences = (payload.evidences || [])
    .map(
      (item) => `
        <article class="card evidence-card">
          <div class="case-tags">
            <span class="tag">${escapeHtml(item.evidenceType || '证据')}</span>
            ${item.workTitle ? `<span class="tag muted">${escapeHtml(item.workTitle)}</span>` : ''}
            ${item.termName ? `<span class="tag muted">${escapeHtml(item.termName)}</span>` : ''}
          </div>
          <p class="detail-paragraph">${escapeHtml(summarizeText(item.snippet || '暂无摘录', 180))}</p>
          <details class="fold-card">
            <summary>展开原文与来源</summary>
            <div class="fold-body">
              ${item.caseTitle ? `<p><strong>所属案例</strong><span><a class="inline-link" href="${buildCaseHref(item.caseId)}">${escapeHtml(item.caseTitle)}</a></span></p>` : ''}
              ${item.sourceLocation ? `<p><strong>定位</strong><span>${escapeHtml(item.sourceLocation)}</span></p>` : ''}
              ${item.quoteText ? `<p><strong>原文</strong><span>${escapeHtml(item.quoteText)}</span></p>` : ''}
              ${item.note ? `<p><strong>备注</strong><span>${escapeHtml(item.note)}</span></p>` : ''}
            </div>
          </details>
        </article>
      `,
    )
    .join('');

  detailMain.innerHTML = `
    <section class="detail-stack">
      <article class="card detail-focus-card">
        <div class="detail-focus-top">
          <div class="detail-glyph">${escapeHtml(payload.term || '字')}</div>
          <div class="detail-focus-copy">
          <div class="case-tags">
              <span class="tag">${escapeHtml(payload.termType || '未分类')}</span>
              <span class="tag muted">${escapeHtml(payload.category || '未分类')}</span>
            </div>
            <p class="detail-lead">${escapeHtml(summarizeText(payload.coreMeaning || payload.notes || '暂无摘要', 220))}</p>
          </div>
        </div>
        ${aliasList ? `<div class="mini-chip-list">${aliasList}</div>` : ''}
      </article>

      <div class="grid grid-2">
        <article class="card">
          <h3>关联案例</h3>
          <div class="detail-card-grid">${relatedCaseGroups.visible.join('') || '<p class="compact-note">暂无关联案例。</p>'}</div>
          ${relatedCaseGroups.hidden.length ? `
            <details class="fold-card inline-fold">
              <summary>展开剩余 ${relatedCaseGroups.hidden.length} 条关联案例</summary>
              <div class="fold-body detail-card-grid">
                ${relatedCaseGroups.hidden.join('')}
              </div>
            </details>
          ` : ''}
        </article>
        <article class="card">
          <h3>证据概况</h3>
          ${evidenceTypeList ? `<div class="schema-meta">${evidenceTypeList}</div>` : '<p class="compact-note">暂无证据类型标注。</p>'}
          ${relatedWorks ? `<div class="term-footer">${relatedWorks}</div>` : ''}
        </article>
      </div>

      <details class="fold-card">
        <summary>证据摘录</summary>
        <div class="fold-body detail-card-grid">
          ${evidences || '<p class="compact-note">暂无证据摘录。</p>'}
        </div>
      </details>
    </section>
  `;
}

async function renderAuditTargets(cases) {
  if (!cases.length) return;
  const section = document.createElement('section');
  section.className = 'card';
  section.innerHTML = '<h2>关联案例释证与审校</h2><p>正在核对来源关系……</p>';
  detailMain.append(section);
  try {
    const targets = {};
    for (let start = 0; start < cases.length; start += 100) {
      Object.assign(targets, await Site.auditLinks('main', cases.slice(start, start + 100).map(item => item.id)));
    }
    section.innerHTML = '<h2>关联案例释证与审校</h2>' + cases.map(item => `
      <p>${escapeHtml(item.displayTitle || item.title)} · ${Site.auditMarkup(targets[item.id])}</p>
    `).join('');
  } catch {
    section.textContent = '审校关联暂不可用，仍可阅读关联案例。';
  }
}

async function init() {
  const id = getRequiredId();
  if (!id) {
    renderDetailNotFound('缺少字词编号。');
    return;
  }
  try {
    const payload = await requestJson(`/api/term?id=${encodeURIComponent(id)}`);
    if (!payload?.ok) throw new Error('字词记录不存在');
    renderTermDetail(payload);
    await renderAuditTargets(payload.relatedCases || []);
  } catch (error) {
    renderDetailNotFound('字词读取失败：' + error.message);
  }
}

init();

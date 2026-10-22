const detailView = document.body.dataset.detailView || '';
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
        <p>请返回首页重新检索，或检查当前链接中的编号是否正确。</p>
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

function renderCaseDetail(payload) {
  if (detailTitle) {
    detailTitle.textContent = payload.displayTitle || payload.title || '未命名案例';
  }
  if (detailLead) {
    detailLead.textContent = summarizeText(payload.conclusion || payload.problem || '当前案例暂无摘要说明。', 150);
  }
  const evidenceTypeList = (payload.evidenceTypes || [])
    .map((type) => `<span class="tag">${escapeHtml(type)}</span>`)
    .join('');
  const relatedWorks = (payload.relatedWorks || [])
    .map((work) => `<span class="term-case-ref">${escapeHtml(work)}</span>`)
    .join('');
  const termGroups = splitItems(payload.terms || [], 10);
  const visibleTermLinks = termGroups.visible
    .map(
      (item) => `
        <a class="mini-chip term-nav-chip" href="${buildTermHref(item.id)}">
          ${escapeHtml(item.term)}
        </a>
      `,
    )
    .join('');
  const hiddenTermLinks = termGroups.hidden
    .map(
      (item) => `
        <a class="mini-chip term-nav-chip" href="${buildTermHref(item.id)}">
          ${escapeHtml(item.term)}
        </a>
      `,
    )
    .join('');
  const evidences = (payload.evidences || [])
    .map(
      (item) => `
        <article class="card evidence-card">
          <div class="case-tags">
            <span class="tag">${escapeHtml(item.evidenceType || '证据')}</span>
            ${item.workTitle ? `<span class="tag muted">${escapeHtml(item.workTitle)}</span>` : ''}
            ${item.termName ? `<a class="tag muted inline-tag-link" href="${buildTermHref(item.termId)}">${escapeHtml(item.termName)}</a>` : ''}
          </div>
          <p class="detail-paragraph">${escapeHtml(summarizeText(item.snippet || item.quoteText || '暂无摘录', 180))}</p>
          <details class="fold-card">
            <summary>展开引文与备注</summary>
            <div class="fold-body">
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
        <div class="case-topline">
          <span class="case-term">${escapeHtml(payload.termLabel || '关联字词')}</span>
          <div class="case-tags">
            <span class="tag">${escapeHtml(payload.method || '未标注方法')}</span>
            <span class="tag muted">${escapeHtml(payload.certainty || '未标注置信度')}</span>
          </div>
        </div>
        ${payload.displaySubtitle ? `<p class="case-subtitle">${escapeHtml(payload.displaySubtitle)}</p>` : ''}
        ${visibleTermLinks ? `<div class="case-members">${visibleTermLinks}</div>` : ''}
        ${hiddenTermLinks ? `
          <details class="fold-card inline-fold">
            <summary>展开剩余 ${termGroups.hidden.length} 个关联字词</summary>
            <div class="fold-body case-members">
              ${hiddenTermLinks}
            </div>
          </details>
        ` : ''}
        <div class="grid grid-2">
          <div class="detail-block">
            <h3>问题</h3>
            <p class="detail-paragraph">${escapeHtml(payload.problem || '暂无问题描述')}</p>
          </div>
          <div class="detail-block">
            <h3>结论</h3>
            <p class="detail-paragraph">${escapeHtml(payload.conclusion || '暂无结论')}</p>
          </div>
        </div>
      </article>

      <div class="grid grid-2">
        <article class="card">
          <h3>出处与来源</h3>
          <div class="detail-list">
            <p><strong>二王出处</strong><span>${escapeHtml(payload.erwangWorkTitle || '未录入')}${payload.erwangLocation ? ` · ${escapeHtml(payload.erwangLocation)}` : ''}</span></p>
            <p><strong>原始文本</strong><span>${escapeHtml(payload.targetWorkTitle || '暂未关联原始经典')}${payload.targetLocation ? ` · ${escapeHtml(payload.targetLocation)}` : ''}</span></p>
          </div>
        </article>
        <article class="card">
          <h3>证据概况</h3>
          ${evidenceTypeList ? `<div class="schema-meta">${evidenceTypeList}</div>` : '<p class="compact-note">暂无证据类型标注。</p>'}
          ${relatedWorks ? `<div class="term-footer">${relatedWorks}</div>` : ''}
        </article>
      </div>

      <details class="fold-card">
        <summary>考据过程</summary>
        <div class="fold-body">
          <p class="detail-paragraph">${escapeHtml(payload.processText || '当前案例暂无过程文本。')}</p>
        </div>
      </details>

      <details class="fold-card">
        <summary>证据链</summary>
        <div class="fold-body detail-card-grid">
          ${evidences || '<p class="compact-note">暂无证据链条。</p>'}
        </div>
      </details>
    </section>
  `;
}

async function init() {
  const id = getRequiredId();
  if (!id) {
    renderDetailNotFound('缺少详情编号。');
    return;
  }

  try {
    const endpoint = detailView === 'term' ? `/api/term?id=${encodeURIComponent(id)}` : `/api/case?id=${encodeURIComponent(id)}`;
    const payload = await requestJson(endpoint);

    if (!payload?.ok) {
      renderDetailNotFound('详情记录不存在。');
      return;
    }

    if (detailView === 'term') {
      renderTermDetail(payload);
      const related = payload.relatedCases || [];
      if (related.length) {
        const target = document.createElement('section'); target.className='card';
        target.innerHTML='<h2>关联案例释证与审校</h2><p>正在核对来源关系……</p>'; detailMain.append(target);
        try { const map=await Site.auditLinks('main',related.slice(0,100).map(c=>c.id));
          target.innerHTML='<h2>关联案例释证与审校</h2>'+related.slice(0,100).map(c=>'<p>'+escapeHtml(c.displayTitle||c.title)+' · '+Site.auditMarkup(map[c.id])+'</p>').join('');
        } catch { target.textContent='审校关联暂不可用，仍可阅读关联案例。'; }
      }
      return;
    }

    renderCaseDetail(payload);
  } catch (error) {
    renderDetailNotFound('详情读取失败，请返回首页重新进入。');
    console.error(error);
  }
}

init();

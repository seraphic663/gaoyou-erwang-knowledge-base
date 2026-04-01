const detailView = document.body.dataset.detailView || '';
const detailTitle = document.querySelector('#detailTitle');
const detailLead = document.querySelector('#detailLead');
const detailMeta = document.querySelector('#detailMeta');
const detailStatus = document.querySelector('#detailStatus');
const detailMain = document.querySelector('#detailMain');

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function requestJson(path) {
  return fetch(path).then((response) => {
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
  });
}

function summarizeText(value, maxLength = 180) {
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

function getRequiredId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('id') || '';
}

function buildTermHref(id) {
  return `./term.html?id=${encodeURIComponent(String(id))}`;
}

function buildCaseHref(id) {
  return `./case.html?id=${encodeURIComponent(String(id))}`;
}

function renderMetaCards(items) {
  if (!detailMeta) return;

  detailMeta.innerHTML = items
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

function renderDetailNotFound(message) {
  if (detailStatus) {
    detailStatus.textContent = message;
  }
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
  renderMetaCards([
    { label: '类型', value: payload.termType || '未分类' },
    { label: '类别', value: payload.category || '未分类' },
    { label: '关联案例', value: `${payload.caseCount || 0} 条` },
    { label: '关联证据', value: `${payload.evidenceCount || 0} 条` },
  ]);

  if (detailStatus) {
    detailStatus.textContent = `数据来源：${payload.sourceLabel}`;
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
          <p class="compact-note">默认只展示前 4 条，剩余案例按需展开。</p>
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
          <p class="compact-note">优先展示证据类型和涉及文献，详细引文放在折叠区。</p>
          ${evidenceTypeList ? `<div class="schema-meta">${evidenceTypeList}</div>` : '<p class="compact-note">暂无证据类型标注。</p>'}
          ${relatedWorks ? `<div class="term-footer">${relatedWorks}</div>` : ''}
        </article>
      </div>

      <details class="fold-card">
        <summary>证据摘录</summary>
        <div class="fold-body detail-card-grid">
          ${evidences || '<p class="compact-note">暂无证据摘录。</p>'}
          ${payload.evidencesTruncated ? '<p class="compact-note">当前仅展示前 12 条证据，更多证据已折叠在数据层，不在页面继续展开。</p>' : ''}
        </div>
      </details>

      <details class="fold-card">
        <summary>原始字段与补充备注</summary>
        <div class="fold-body">
          <p><strong>词条编号</strong><span>${escapeHtml(String(payload.raw?.id || ''))}</span></p>
          <p><strong>case_ids</strong><span>${escapeHtml(JSON.stringify(payload.raw?.case_ids || []))}</span></p>
          <p><strong>core_meaning</strong><span>${escapeHtml(payload.coreMeaning || '无')}</span></p>
          <p><strong>notes</strong><span>${escapeHtml(payload.notes || '无')}</span></p>
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
  renderMetaCards([
    { label: '方法', value: payload.method || '未标注方法' },
    { label: '置信度', value: payload.certainty || '未标注置信度' },
    { label: '状态', value: payload.status || '未标注状态' },
    { label: '证据', value: `${payload.evidenceCount || 0} 条` },
  ]);

  if (detailStatus) {
    detailStatus.textContent = `数据来源：${payload.sourceLabel}`;
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
          ${item.quoteText && item.quoteText !== item.snippet ? `<p class="compact-note">摘录已压缩，完整引文见下方折叠区。</p>` : ''}
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
          ${payload.evidencesTruncated ? '<p class="compact-note">当前仅展示前 12 条证据，页面不再继续堆叠。</p>' : ''}
        </div>
      </details>

      <details class="fold-card">
        <summary>原始字段</summary>
        <div class="fold-body">
          <p><strong>案例编号</strong><span>${escapeHtml(String(payload.raw?.id || ''))}</span></p>
          <p><strong>term_ids</strong><span>${escapeHtml(JSON.stringify(payload.raw?.term_ids || []))}</span></p>
          <p><strong>erwang_passage_id</strong><span>${escapeHtml(String(payload.raw?.erwang_passage_id ?? 'null'))}</span></p>
          <p><strong>target_passage_id</strong><span>${escapeHtml(String(payload.raw?.target_passage_id ?? 'null'))}</span></p>
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
      return;
    }

    renderCaseDetail(payload);
  } catch (error) {
    renderDetailNotFound('详情读取失败，请返回首页重新进入。');
    console.error(error);
  }
}

init();

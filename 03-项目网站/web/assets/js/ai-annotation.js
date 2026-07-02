const annotationAiInput = document.querySelector('#annotationAiInput');
const annotationAiButton = document.querySelector('#annotationAiButton');
const annotationAiClearButton = document.querySelector('#annotationAiClearButton');
const annotationAiResult = document.querySelector('#annotationAiResult');

function parseAiAnswer(answer) {
  const text = String(answer || '')
    .trim()
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '');
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  const candidates = [
    text,
    start >= 0 && end > start ? text.slice(start, end + 1) : '',
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === 'object') return parsed;
    } catch {
      continue;
    }
  }

  return null;
}

function renderAiSection(title, content) {
  const items = Array.isArray(content) ? content.filter(Boolean) : [content].filter(Boolean);
  const safeItems = items.length ? items : ['本栏本次未返回内容，需人工补写或重新解析。'];
  return `
    <section class="annotation-ai-section">
      <h3>${escapeHtml(title)}</h3>
      ${safeItems.length === 1
        ? `<p>${escapeHtml(safeItems[0])}</p>`
        : `<ol>${safeItems.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ol>`}
    </section>
  `;
}

function renderAiAnswer(answer, structuredAnswer = null) {
  const parsed = structuredAnswer || parseAiAnswer(answer);
  const structured = parsed ? {
    judgment: parsed.judgment || '本次模型未返回明确判断，需人工依据下列材料补写。',
    evidences: parsed.evidences || ['本次模型未返回可用证据条目，需回到人工标注库核对。'],
    draft: parsed.draft || ['本次模型未返回解析草案，需人工按“立论—取证—释理—结论”补写。'],
    reviewNotes: parsed.reviewNotes || ['本次模型未返回核对事项，需人工复核原文、证据方向与案例粒度。'],
  } : null;

  if (!structured) {
    return `<pre>${escapeHtml(answer || '未返回内容')}</pre>`;
  }

  return `
    <div class="annotation-ai-report">
      ${renderAiSection('判断', structured.judgment)}
      ${renderAiSection('可用证据', structured.evidences)}
      ${renderAiSection('解析草案', structured.draft)}
      ${renderAiSection('仍需人工核对处', structured.reviewNotes)}
    </div>
  `;
}

function flattenSources(sources = {}) {
  const annotationItems = (sources.annotation || []).map((item, index) => ({
    id: `annotation-${index}`,
    typeLabel: '人工标注库',
    title: item.title || '未题名案例',
    subtitle: item.document || item.sourceWork || '',
    core: item.claim || item.claimCore || item.problem || '未返回核心判断',
    fullBlocks: [
      ['来源文档', item.document],
      ['来源著作', item.sourceWork],
      ['核心判断', item.claimFull || item.claim],
      ['方法标签', (item.methods || []).join('、')],
      ['相关步骤', (item.relevantSteps || []).map((step) => step.full || step.core || step).join('\n')],
      ['相关证据', (item.evidences || []).map((evidence) => {
        const work = evidence.work ? `《${evidence.work}》` : '未标注来源';
        const role = evidence.role ? `（${evidence.role}）` : '';
        return `${work}${role}：${evidence.quoteFull || evidence.quote || evidence.quoteCore || ''}`;
      }).join('\n')],
    ],
  }));

  const mainItems = (sources.main || []).map((item, index) => ({
    id: `main-${index}`,
    typeLabel: '主数据库补充',
    title: item.title || '未题名案例',
    subtitle: item.subtitle || item.term || '',
    core: item.conclusion || item.preview || '未返回核心判断',
    fullBlocks: [
      ['相关字词', item.term],
      ['方法', item.method],
      ['结论', item.conclusion],
      ['证据摘录', (item.evidences || []).join('\n')],
    ],
  }));

  return [...annotationItems, ...mainItems];
}

function renderReferenceFull(item) {
  const blocks = item.fullBlocks
    .filter(([, value]) => String(value || '').trim())
    .map(([label, value]) => `
      <div class="ai-reference-block">
        <strong>${escapeHtml(label)}</strong>
        <p>${escapeHtml(value)}</p>
      </div>
    `)
    .join('');

  return blocks || '<p class="compact-note">该条引用没有更多可展开内容。</p>';
}

function renderReferences(sources = {}) {
  const items = flattenSources(sources);
  if (!items.length) {
    return '<p class="compact-note">本次没有返回可核对引用。</p>';
  }

  return `
    <section class="ai-reference-panel" data-reference-panel>
      <div class="ai-reference-head">
        <div>
          <p class="section-kicker">引用材料</p>
          <h3>本次引用 ${escapeHtml(items.length)} 条数据库材料</h3>
        </div>
        <button class="search-clear toolbar-button" type="button" data-toggle-references>展开引用</button>
      </div>
      <div class="ai-reference-list" hidden>
        <div class="toolbar-actions ai-reference-actions">
          <button class="page-link toolbar-button" type="button" data-expand-all-references>全部展开</button>
          <button class="search-clear toolbar-button" type="button" data-collapse-all-references>全部收起</button>
        </div>
        ${items.map((item) => `
          <article class="ai-reference-item" data-reference-item>
            <div class="ai-reference-core">
              <div>
                <span class="summary-pill">${escapeHtml(item.typeLabel)}</span>
                <h4>${escapeHtml(item.title)}</h4>
                ${item.subtitle ? `<p class="compact-note">${escapeHtml(item.subtitle)}</p>` : ''}
              </div>
              <button class="detail-link ai-reference-toggle" type="button" data-toggle-reference-item>展开全文</button>
            </div>
            <p class="ai-reference-excerpt">${escapeHtml(item.core)}</p>
            <div class="ai-reference-full" hidden>
              ${renderReferenceFull(item)}
            </div>
          </article>
        `).join('')}
      </div>
    </section>
  `;
}

function bindReferenceControls(root) {
  root.querySelector('[data-toggle-references]')?.addEventListener('click', (event) => {
    const panel = event.target.closest('[data-reference-panel]');
    const list = panel?.querySelector('.ai-reference-list');
    if (!list) return;
    const nextHidden = !list.hidden;
    list.hidden = nextHidden;
    event.target.textContent = nextHidden ? '展开引用' : '收起引用';
  });

  root.querySelectorAll('[data-toggle-reference-item]').forEach((button) => {
    button.addEventListener('click', () => {
      const item = button.closest('[data-reference-item]');
      const body = item?.querySelector('.ai-reference-full');
      if (!body) return;
      body.hidden = !body.hidden;
      button.textContent = body.hidden ? '展开全文' : '收起全文';
    });
  });

  root.querySelector('[data-expand-all-references]')?.addEventListener('click', (event) => {
    const panel = event.target.closest('[data-reference-panel]');
    panel?.querySelectorAll('.ai-reference-full').forEach((body) => { body.hidden = false; });
    panel?.querySelectorAll('[data-toggle-reference-item]').forEach((button) => { button.textContent = '收起全文'; });
  });

  root.querySelector('[data-collapse-all-references]')?.addEventListener('click', (event) => {
    const panel = event.target.closest('[data-reference-panel]');
    panel?.querySelectorAll('.ai-reference-full').forEach((body) => { body.hidden = true; });
    panel?.querySelectorAll('[data-toggle-reference-item]').forEach((button) => { button.textContent = '展开全文'; });
  });
}

async function runAnnotationAi() {
  const question = annotationAiInput?.value.trim() || '';
  if (!question) {
    annotationAiResult.innerHTML = '<p class="compact-note">请输入需要解析的内容。</p>';
    return;
  }

  annotationAiButton.disabled = true;
  annotationAiResult.innerHTML = '<p class="compact-note">正在检索人工库并调用 AI...</p>';

  try {
    const response = await fetch('/api/ai/annotation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const payload = await response.json();

    if (!payload.ok) {
      annotationAiResult.innerHTML = `
        <p class="compact-note">${escapeHtml(payload.message || 'AI 解析失败')}</p>
        ${renderReferences(payload.sources)}
      `;
      bindReferenceControls(annotationAiResult);
      return;
    }

    annotationAiResult.innerHTML = `
      ${renderAiAnswer(payload.answer, payload.structuredAnswer)}
      ${renderReferences(payload.sources)}
    `;
    bindReferenceControls(annotationAiResult);
  } catch (error) {
    annotationAiResult.innerHTML = `<p class="compact-note">AI 接口不可用：${escapeHtml(error.message)}</p>`;
  } finally {
    annotationAiButton.disabled = false;
  }
}

annotationAiButton?.addEventListener('click', runAnnotationAi);

annotationAiClearButton?.addEventListener('click', () => {
  annotationAiInput.value = '';
  annotationAiResult.textContent = '尚未解析。';
});

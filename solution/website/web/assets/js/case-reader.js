(async () => {
  const params = new URLSearchParams(location.search);
  const source = params.get('source');
  const id = params.get('id');
  const root = document.querySelector('#caseReader');
  const title = document.querySelector('#detailTitle');

  const section = (heading, content, id = "") => `<section class="card"${id ? ` id="${id}"` : ""}><h2>${heading}</h2>${content}</section>`;
  const paragraph = value => `<p class="detail-paragraph">${escapeHtml(value || '未记录')}</p>`;
  const field = (label, value) => `<div class="detail-block"><h3>${label}</h3>${paragraph(value)}</div>`;
  const rawFields = value => `
    <details class="fold-card">
      <summary>查看完整来源字段</summary>
      <pre class="site-raw">${escapeHtml(JSON.stringify(value, null, 2))}</pre>
    </details>
  `;

  function renderTerm(term) {
    const label = term.id
      ? Site.link(Site.url('/term', { id: term.id, return: Site.current() }), term.label)
      : `<strong>${escapeHtml(term.label)}</strong>`;
    return `<p>${label} ${escapeHtml(term.relation || '')}</p>${term.note ? paragraph(term.note) : ''}`;
  }

  function renderEvidence(evidence) {
    const status = evidence.status === 'unchecked' ? '引文尚未核对原典' : evidence.status;
    return `
      <article class="evidence-card">
        <h3>${escapeHtml(evidence.work || '来源未注明')}</h3>
        <p class="compact-note">${escapeHtml([evidence.kind, status].filter(Boolean).join(' · '))}</p>
        ${evidence.term ? Site.link(Site.url('/term', { id: evidence.term.id, return: Site.current() }), evidence.term.label) : ''}
        <blockquote>${paragraph(evidence.quote)}</blockquote>
        ${evidence.location ? field('出处位置', evidence.location) : ''}
        ${evidence.note ? field('说明', evidence.note) : ''}
        ${rawFields(evidence.raw)}
      </article>
    `;
  }

  function renderCase(model) {
    const passages = model.passages.map(passage => section(
      passage.label,
      paragraph(passage.location) + paragraph(passage.text) + rawFields(passage.raw),
    )).join('');
    const related = model.relatedCases.map(item => Site.link(Site.caseUrl(item.source, item.id), item.title)).join(' ');
    return `
      <div class="site-actions">
        <span class="tag">${escapeHtml(model.sourceLabel)}</span>
        <span id="caseAudit">核对审校关联中……</span>
        ${Site.link(Site.url('/corpus', { ...model.corpusQuery, return: Site.current() }), model.corpusLabel)}
        ${Site.link(Site.url('/knowledge', { return: Site.current() }), '查看训诂方法')}
      </div>
      <nav class="site-jump-links" aria-label="案例内容">
        <a href="#case-judgment">问题与判断</a><a href="#case-provenance">出处与状态</a>
        <a href="#case-terms">相关字词</a><a href="#case-evidence">证据</a><a href="#case-process">考据过程</a>
      </nav>
      ${section('问题与判断', field('目标文字', model.targetText) + field('问题', model.problem)
        + field('主张 / 设问', model.claim) + field('结论', model.conclusion), 'case-judgment')}
      ${passages}
      ${section('出处与状态', field('材料来源', model.origin) + field('来源位置', model.sourceLocation)
        + field('目标典籍与位置', model.targetLocation) + field('材料状态', model.status)
        + (model.methods ? field('方法', model.methods) : ''), 'case-provenance')}
      ${section('相关字词', `<div class="site-term-grid">${model.terms.map(renderTerm).join('') || paragraph('未记录')}</div>`, 'case-terms')}
      ${section('证据', model.evidence.map(renderEvidence).join('') || paragraph('未记录'), 'case-evidence')}
      ${section('考据过程', model.steps.map(step => field(escapeHtml(step.label), step.text)).join('') || paragraph('未记录'), 'case-process')}
      ${related ? section('相关案例', related) : ''}
      ${rawFields(model.raw)}
    `;
  }

  try {
    if (!id) throw new Error('缺少案例编号');
    const payload = await requestJson(CaseSources.detailUrl(source, id));
    const model = CaseSources.detail(source, payload);
    title.textContent = model.title;
    root.innerHTML = renderCase(model);
    try {
      const targets = await Site.auditLinks(source, [id]);
      document.querySelector('#caseAudit').innerHTML = Site.auditMarkup(targets[id]);
    } catch {
      document.querySelector('#caseAudit').textContent = '暂时无法核对审校关联';
    }
  } catch (error) {
    root.textContent = '无法读取案例：' + error.message;
  }
})();

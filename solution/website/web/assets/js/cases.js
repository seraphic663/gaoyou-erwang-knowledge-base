(() => {
  const params = new URLSearchParams(location.search);
  const selectedSource = params.get('source') || 'all';
  const form = document.querySelector('#caseSearch');
  const results = document.querySelector('#caseResults');
  const sources = CaseSources.sources.filter(source => selectedSource === 'all' || source.id === selectedSource);

  function renderCard(item, index) {
    return `
      <article class="card site-case">
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.summary)}</p>
        <p class="compact-note">${escapeHtml(item.origin)} · ${escapeHtml(item.status)}</p>
        <div class="site-actions">
          ${Site.link(Site.caseUrl(item.source, item.id), '查看案例')}
          <span data-audit-index="${index}">正在核对审校关联……</span>
        </div>
      </article>
    `;
  }

  async function loadAuditLinks(section, source, items) {
    if (!items.length) return;
    const placeholders = section.querySelectorAll('[data-audit-index]');
    try {
      const targets = await Site.auditLinks(source, items.map(item => item.id));
      placeholders.forEach((element, index) => {
        element.innerHTML = Site.auditMarkup(targets[items[index].id]);
      });
    } catch {
      placeholders.forEach(element => {
        element.textContent = '审校关联暂不可用，仍可阅读原记录';
      });
    }
  }

  async function loadSource(source) {
    const section = document.querySelector('#source-' + source.id);
    try {
      const payload = await requestJson(CaseSources.listUrl(source.id, params));
      const page = CaseSources.list(source.id, payload);
      section.innerHTML = `
        <h2>${escapeHtml(source.label)} <small>${page.total} 条</small></h2>
        <p class="compact-note">保留原始来源身份；各来源可能有迁移或重叠记录，不合并计作独立案例。</p>
        ${page.items.map(renderCard).join('') || '<p>没有匹配记录。</p>'}
        ${Site.pagination('/cases', params, page.page, page.pages, 'page_' + source.id)}
      `;
      if (source.id === 'v2') {
        form.elements.source_work.innerHTML = Site.options([
          { value: '', label: '全部来源' },
          ...page.sourceWorks.map(work => ({ value: work, label: work })),
        ]);
        form.elements.source_work.value = params.get('source_work') || '';
      }
      await loadAuditLinks(section, source.id, page.items);
    } catch (error) {
      section.innerHTML = `<h2>${escapeHtml(source.label)}</h2><p role="alert">${escapeHtml(error.message)}</p>`;
    }
  }

  async function loadAnnotationFilters() {
    try {
      const data = await requestJson('/api/annotation/bootstrap');
      for (const [field, values] of [['annotator', data.annotators], ['origin', data.origins]]) {
        form.elements[field].innerHTML = Site.options(values || []);
        form.elements[field].value = params.get(field) || 'all';
      }
    } catch {
      document.querySelector('#caseFilterStatus').textContent = '人工标注筛选选项暂不可用，仍可检索关键词。';
    }
  }

  function updateFilterVisibility() {
    const source = form.elements.source.value;
    form.querySelectorAll('[data-filter-source]').forEach(label => {
      const visible = source === 'all' || source === label.dataset.filterSource;
      label.hidden = !visible;
      label.querySelector('select').disabled = !visible;
    });
    document.querySelector('#caseAdvancedFilters').hidden = source === 'main';
  }

  function init() {
    document.querySelector('#caseAdvancedFilters').open = ['annotator', 'origin', 'source_work', 'machine_status'].some(key => params.get(key) && params.get(key) !== 'all');
    form.elements.q.value = params.get('q') || '';
    form.elements.source.innerHTML = Site.options([
      { value: 'all', label: '全部来源' },
      ...CaseSources.sources.map(source => ({ value: source.id, label: source.label })),
    ]);
    form.elements.source.value = selectedSource;
    form.elements.source.onchange = updateFilterVisibility;
    updateFilterVisibility();
    form.elements.machine_status.value = params.get('machine_status') || '';
    form.onsubmit = event => {
      event.preventDefault();
      location.href = '/cases?' + new URLSearchParams(new FormData(form));
    };
    if (!sources.length) {
      results.textContent = '未知材料来源，请重新选择。';
      return;
    }
    results.innerHTML = sources.map(source => `
      <section class="site-source" id="source-${source.id}">
        <h2>${escapeHtml(source.label)}</h2><p>正在读取……</p>
      </section>
    `).join('');
    loadAnnotationFilters();
    sources.forEach(loadSource);
  }

  init();
})();

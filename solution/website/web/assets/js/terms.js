(() => {
  const params = new URLSearchParams(location.search);
  const form = document.querySelector('#termSearch');
  const root = document.querySelector('#termResults');

  function renderTerm(item) {
    const related = (item.relatedCases || []).map(relatedCase =>
      Site.link(Site.caseUrl('main', relatedCase.id), relatedCase.displayTitle || relatedCase.title || '关联案例'));
    return `
      <article class="card">
        <h2>${Site.link(Site.url('/term', { id: item.id, return: Site.current() }), item.term)}</h2>
        <p>${escapeHtml(item.coreMeaning || item.notes || '')}</p>
        <div class="site-actions">${related.join('')}</div>
      </article>
    `;
  }

  async function loadCategories() {
    try {
      const data = await requestJson('/api/browser/bootstrap');
      form.elements.category.innerHTML = Site.options(data.termCategories || []);
      form.elements.category.value = params.get('category') || 'all';
    } catch {
      document.querySelector('#termFilterStatus').textContent = '类别筛选暂不可用，仍可检索关键词。';
    }
  }

  async function loadTerms() {
    const query = new URLSearchParams({
      view: 'terms', mode: params.get('mode') || 'fulltext',
      category: params.get('category') || 'all', q: params.get('q') || '',
      page: params.get('page') || '1', pageSize: '30',
    });
    try {
      const data = await requestJson('/api/browser?' + query);
      root.innerHTML = `
        <p>${data.total} 条字词</p>
        <div class="grid grid-2">${data.items.map(renderTerm).join('')}</div>
        ${Site.pagination('/terms', params, data.page, data.totalPages)}
      `;
    } catch (error) {
      root.textContent = '字词读取失败：' + error.message;
    }
  }

  form.elements.q.value = params.get('q') || '';
  form.elements.mode.value = params.get('mode') || 'fulltext';
  form.onsubmit = event => {
    event.preventDefault();
    location.href = '/terms?' + new URLSearchParams(new FormData(form));
  };
  loadCategories();
  loadTerms();
})();

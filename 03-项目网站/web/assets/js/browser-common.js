const BrowserCommon = (() => {
  function renderHeroItems(target, items) {
    if (!target) return;

    target.innerHTML = items
      .map((item) => `
        <div class="hero-panel-item">
          <span class="hero-kicker">${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
        </div>
      `)
      .join('');
  }

  function renderChoiceButtons(target, items, options = {}) {
    if (!target) return;

    const {
      activeValue = 'all',
      activeValues = null,
      valueAttribute = 'data-value',
      className = 'filter-chip',
      emptyText = '暂无可用筛选。',
    } = options;

    const isActive = (value) => {
      if (activeValues instanceof Set) return activeValues.has(value);
      if (Array.isArray(activeValues)) return activeValues.includes(value);
      return value === activeValue;
    };

    target.innerHTML = items
      .map((item) => {
        const value = String(item.value ?? item.label ?? '');
        const count = item.count ?? '';
        const countHtml = count === '' || count === null || count === undefined
          ? ''
          : `<span class="filter-count">${escapeHtml(String(count))}</span>`;
        return `
          <button class="${className}${isActive(value) ? ' active' : ''}" type="button" ${valueAttribute}="${escapeHtml(value)}">
            <span class="filter-label">${escapeHtml(item.label ?? value)}</span>
            ${countHtml}
          </button>
        `;
      })
      .join('') || `<p class="compact-note sidebar-empty">${escapeHtml(emptyText)}</p>`;
  }

  function renderSchemaCards(target, stores) {
    if (!target) return;

    target.innerHTML = (stores || [])
      .map((store) => `
        <article class="card schema-card">
          <div class="schema-card-head">
            <h3>${escapeHtml(store.label)}</h3>
            <span>${escapeHtml(String(store.count || 0))}</span>
          </div>
          <p>${escapeHtml(store.purpose)}</p>
        </article>
      `)
      .join('');
  }

  function includesText(values, query) {
    if (!query) return true;
    const needle = query.toLowerCase();
    return values.some((value) => String(value || '').toLowerCase().includes(needle));
  }

  return {
    includesText,
    renderChoiceButtons,
    renderHeroItems,
    renderSchemaCards,
  };
})();

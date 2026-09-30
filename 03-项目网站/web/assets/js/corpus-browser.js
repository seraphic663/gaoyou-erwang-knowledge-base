(() => {
  const state = { requestId: 0 };
  const elements = {
    status: document.querySelector('#corpusStatus'),
    resultCount: document.querySelector('#corpusResultCount'),
    form: document.querySelector('#corpusSearchForm'),
    query: document.querySelector('#corpusQuery'),
    work: document.querySelector('#corpusWork'),
    searchButton: document.querySelector('#corpusSearchButton'),
    reset: document.querySelector('#corpusReset'),
    searchStatus: document.querySelector('#corpusSearchStatus'),
    results: document.querySelector('#corpusResults'),
  };

  const workLabels = {
    dushu_zazhi: '《读书杂志》',
    guangya_shuzheng: '《广雅疏证》',
    jingyi_shuwen: '《经义述闻》',
    jingzhuan_shici: '《经传释词》',
  };

  function labelForWork(workKey) {
    return workLabels[String(workKey || '')] || String(workKey || '作品未注明');
  }

  function relationLabel(relation) {
    return relation === 'source_passage' ? '案例来源段落' : '案例证据段落';
  }

  function populateWorkFilter() {
    if (!elements.work) return;
    elements.work.innerHTML = [
      '<option value="all">四部著作</option>',
      ...Object.entries(workLabels).map(([value, label]) => (
        `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`
      )),
    ].join('');
  }

  function renderResults(payload) {
    const items = Array.isArray(payload?.items) ? payload.items : [];
    elements.resultCount.textContent = items.length ? `找到 ${items.length} 段` : '没有结果';
    if (!items.length) {
      elements.results.innerHTML = '<div class="corpus-empty">没有找到对应的 canonical 正文段落。</div>';
      return;
    }

    elements.results.innerHTML = items.map((item, index) => {
      const location = [item.document_title, item.section_title, item.entry_title]
        .filter(Boolean).join(' · ') || labelForWork(item.work_key);
      const cases = Array.isArray(item.related_cases) ? item.related_cases : [];
      const caseMarkup = cases.length
        ? `
          <div class="corpus-related-block">
            <div class="corpus-detail-topline"><strong>关联案例</strong><span class="summary-pill">${escapeHtml(String(cases.length))} 条</span></div>
            <div class="corpus-related-list">
              ${cases.map((caseItem) => `
                <a class="corpus-related-case" href="./v2-database.html?case=${encodeURIComponent(caseItem.case_id)}#browse">
                  <span><strong>${escapeHtml(caseItem.case_title || '未命名案例')}</strong><small>${escapeHtml(caseItem.target_work || '目标典籍未明确')} · ${escapeHtml(caseItem.target_text || '目标文字未记录')}</small></span>
                  <span class="corpus-related-tags">${(caseItem.relations || []).map((relation) => `<span class="corpus-tag">${escapeHtml(relationLabel(relation))}</span>`).join('')}</span>
                </a>
              `).join('')}
            </div>
          </div>
        `
        : '<p class="corpus-note">当前正文还没有关联案例。</p>';
      return `
        <article class="corpus-result">
          <div class="corpus-detail-topline">
            <div class="corpus-result-title"><span class="corpus-rank">${escapeHtml(String(index + 1))}</span><span><strong>${escapeHtml(location)}</strong><small>${escapeHtml(labelForWork(item.work_key))} · ${escapeHtml(item.match_reason || '正文片段命中')}</small></span></div>
            <span class="corpus-status-chip">canonical</span>
          </div>
          <p class="corpus-result-text">${escapeHtml(item.passage_text || '没有可展示的正文。')}</p>
          <p class="corpus-result-meta"><code>${escapeHtml(item.passage_id || '')}</code>${item.md_line_start ? ` · 原文行 ${escapeHtml(String(item.md_line_start))}-${escapeHtml(String(item.md_line_end || item.md_line_start))}` : ''}</p>
          ${caseMarkup}
        </article>
      `;
    }).join('');
  }

  async function runSearch() {
    const query = String(elements.query?.value || '').trim();
    const workKey = elements.work?.value || 'all';
    if (!query) {
      elements.searchStatus.textContent = '输入一段正文后检索。';
      elements.resultCount.textContent = '尚未检索';
      elements.results.innerHTML = '';
      return;
    }

    const requestId = ++state.requestId;
    elements.searchButton.disabled = true;
    elements.searchStatus.textContent = '正在查找已登记的 canonical 正文……';
    elements.results.innerHTML = '<div class="corpus-empty">正在读取正文结果……</div>';
    const params = new URLSearchParams({ q: query, limit: '8', include_cases: '1' });
    if (workKey !== 'all') params.set('work_key', workKey);
    try {
      const payload = await requestJson(`/api/corpus/retrieve?${params.toString()}`);
      if (requestId !== state.requestId) return;
      renderResults(payload);
      const count = Number(payload.returned_count ?? payload.items?.length ?? 0);
      const caseCount = (payload.items || []).reduce((total, item) => total + (item.related_cases?.length || 0), 0);
      elements.searchStatus.textContent = count
        ? `找到 ${count} 段正文；其中 ${caseCount} 条带有关联案例。`
        : '没有找到对应的 canonical 正文段落。';
      elements.status.textContent = `通用语料库已连接 · ${payload.trace?.retrieval_method || '只读正文检索'} · 结果不写入数据库`;
    } catch (error) {
      if (requestId !== state.requestId) return;
      elements.results.innerHTML = `<div class="corpus-empty">正文检索失败：${escapeHtml(error.message)}</div>`;
      elements.searchStatus.textContent = '请稍后重试。';
      elements.resultCount.textContent = '检索失败';
    } finally {
      if (requestId === state.requestId) elements.searchButton.disabled = false;
    }
  }

  elements.form?.addEventListener('submit', (event) => {
    event.preventDefault();
    runSearch();
  });
  elements.reset?.addEventListener('click', () => {
    elements.query.value = '';
    elements.work.value = 'all';
    elements.searchStatus.textContent = '输入一段正文后检索。';
    elements.resultCount.textContent = '尚未检索';
    elements.results.innerHTML = '';
  });
  populateWorkFilter();
  elements.status.textContent = '通用语料库检索已就绪 · canonical 正文只读';
})();

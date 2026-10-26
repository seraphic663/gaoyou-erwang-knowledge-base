(() => {
  const state = { requestId: 0, titleOffset: 0, items: [], counts: null };
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
  const collectionLabels = {
    original: '二王原典',
    external_high: '外典·高频',
    external_mid: '外典·中频',
    external_low: '外典·低频',
  };

  function labelForWork(workKey) {
    return workLabels[String(workKey || '')] || String(workKey || '作品未注明');
  }

  function relationLabel(relation) {
    return ({ source_passage: '案例来源段落', target_passage: '案例目标段落', evidence_passage: '案例证据段落' })[relation] || '案例关联段落';
  }

  function selectedMode() {
    return document.querySelector('input[name="corpusMode"]:checked')?.value || 'unified';
  }

  function selectedCollections() {
    return [...document.querySelectorAll('input[name="corpusCollection"]:checked')].map((input) => input.value);
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

  function stableItems(items, append) {
    const combined = append ? [...state.items, ...items] : items;
    const seen = new Set();
    return combined.filter((item) => {
      const id = String(item.result_id || item.passage_id || item.chunk_id || item.source_id || '');
      const key = `${item.kind || 'original_passage'}:${id}`;
      if (!id || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function renderRelatedCases(cases) {
    if (!cases.length) return '<p class="corpus-note">当前正文还没有关联案例。</p>';
    return `
      <div class="corpus-related-block">
        <div class="corpus-detail-topline"><strong>关联案例</strong><span class="summary-pill">${escapeHtml(String(cases.length))} 条</span></div>
        <div class="corpus-related-list">
          ${cases.map((caseItem) => `
            <a class="corpus-related-case" href="${escapeHtml(Site.caseUrl('v2', caseItem.case_id))}">
              <span><strong>${escapeHtml(plainTextFromMarkup(caseItem.case_title || '未命名案例'))}</strong><small>${escapeHtml(caseItem.target_work || '目标典籍未明确')} · ${escapeHtml(plainTextFromMarkup(caseItem.target_text || '目标文字未记录'))}</small></span>
              <span class="corpus-related-tags">${(caseItem.relations || []).map((relation) => `<span class="corpus-tag">${escapeHtml(relationLabel(relation))}</span>`).join('')}</span>
            </a>${Site.link(Site.auditUrl(caseItem.case_id), '开始本案释证与审校')}
          `).join('')}
        </div>
      </div>
    `;
  }

  function renderItem(item, index) {
    const kind = item.kind || 'original_passage';
    const collectionLabel = item.collection_label || collectionLabels[item.collection] || labelForWork(item.work_key);
    const sourceTitle = item.source_title || item.document_title || labelForWork(item.work_key);
    const location = item.location || [item.document_title, item.section_title, item.entry_title]
      .filter(Boolean).join(' · ') || sourceTitle;
    const label = item.match_label || (item.match_scope === 'title' ? '书名命中' : '正文命中');
    const meta = [];
    if (item.relpath) meta.push(item.relpath);
    if (item.md_line_start) meta.push(`原文行 ${item.md_line_start}-${item.md_line_end || item.md_line_start}`);
    if (item.line_start) meta.push(`原文行 ${item.line_start}-${item.line_end || item.line_start}`);
    const matchedText = item.matched_text || item.passage_text || item.full_text || '';
    const relatedCases = Array.isArray(item.related_cases) ? item.related_cases : [];
    let expansion = '';

    if (kind === 'external_chunk' && item.context_text) {
      const contextStart = item.context_start_cp ?? item.reading_start_cp;
      const contextEnd = item.context_end_cp ?? item.reading_end_cp;
      const lineStart = item.evidence_line_start ?? item.reading_line_start ?? item.line_start;
      const lineEnd = item.evidence_line_end ?? item.reading_line_end ?? item.line_end;
      expansion = `
        <details class="corpus-context-fold">
          <summary>展开邻接原文${lineStart ? `（行 ${escapeHtml(String(lineStart))}-${escapeHtml(String(lineEnd || lineStart))}` : ''}${contextStart !== undefined ? `${lineStart ? '，' : '（'}字符 ${escapeHtml(String(contextStart))}-${escapeHtml(String(contextEnd))}` : ''}${lineStart || contextStart !== undefined ? '）' : ''}</summary>
          <pre>${escapeHtml(item.context_text)}</pre>
        </details>
      `;
    } else if (kind === 'external_source') {
      expansion = `
        <details class="corpus-context-fold" data-source-id="${escapeHtml(item.source_id || '')}">
          <summary>书名命中；正文尚未定位，展开篇首原文</summary>
          <div class="corpus-source-opening">展开后读取该书的篇首切分。</div>
        </details>
      `;
    } else if (item.text_truncated) {
      expansion = `
        <details class="corpus-context-fold">
          <summary>展开返回的原典命中段落</summary>
          <pre>${escapeHtml(matchedText)}</pre>
        </details>
      `;
    }

    const title = kind === 'external_source'
      ? sourceTitle
      : `${sourceTitle}${item.chapter && item.chapter !== sourceTitle ? ` · ${item.chapter}` : ''}`;
    const matchText = kind === 'external_source'
      ? `<p class="corpus-result-text corpus-title-match">书名或路径包含：${escapeHtml(matchedText || sourceTitle)}</p>`
      : `<p class="corpus-result-text">${escapeHtml(matchedText || '没有可展示的命中文段。')}</p>`;

    return `
      <article class="corpus-result">
        <div class="corpus-detail-topline">
          <div class="corpus-result-title">
            <span class="corpus-rank">${escapeHtml(String(index + 1))}</span>
            <span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(collectionLabel)} · ${escapeHtml(location)}</small></span>
          </div>
          <span class="corpus-status-chip">${escapeHtml(label)}</span>
        </div>
        ${matchText}
        <p class="corpus-result-meta">${meta.map((value) => escapeHtml(String(value))).join(' · ')}</p>
        ${expansion}
        ${relatedCases.length ? renderRelatedCases(relatedCases) : ''}
      </article>
    `;
  }

  function renderCounts(counts) {
    const parts = [];
    if (counts?.original?.returned_count) {
      const originalCandidates = counts.original.candidate_count_capped
        ? `至少 ${counts.original.candidate_count} 条（查询候选上限）`
        : `${counts.original.candidate_count} 条`;
      parts.push(`二王原典显示前 ${counts.original.returned_count} 条，当前查询候选 ${originalCandidates}`);
    }
    if (counts?.external_body?.returned_count) {
      parts.push(`外典正文显示前 ${counts.external_body.returned_count} 条（单次最多 ${counts.external_body.result_limit || 6} 条），索引候选 ${counts.external_body.candidate_count} 段`);
    }
    if (counts?.external_title?.total) {
      const loaded = Number(counts.external_title.offset || 0) + Number(counts.external_title.returned_count || 0);
      parts.push(`书名/路径共 ${counts.external_title.total} 项，当前已加载 ${Math.min(loaded, counts.external_title.total)} 项`);
    }
    return parts;
  }

  function renderResults(payload, { append = false } = {}) {
    const items = Array.isArray(payload?.items) ? payload.items : [];
    state.items = stableItems(items, append);
    state.counts = payload?.counts || state.counts;
    elements.resultCount.textContent = state.items.length ? `当前显示 ${state.items.length} 条` : '没有结果';
    if (!state.items.length) {
      elements.results.innerHTML = '<div class="corpus-empty">当前检索范围没有返回匹配项。外典正文只提供字面线索，未命中不代表全库无相关材料。</div>';
      return;
    }

    const rendered = state.items.map(renderItem).join('');
    const titleInfo = state.counts?.external_title;
    const titleHasMore = titleInfo && Number(titleInfo.offset || 0) + Number(titleInfo.returned_count || 0) < Number(titleInfo.total || 0);
    const moreButton = titleHasMore
      ? `<button id="corpusMoreTitles" class="search-clear toolbar-button" type="button">加载更多书名结果（${escapeHtml(String(Math.max(0, Number(titleInfo.total) - Number(titleInfo.offset) - Number(titleInfo.returned_count))))} 项）</button>`
      : '';
    elements.results.innerHTML = rendered + (moreButton ? `<div class="corpus-more-actions">${moreButton}</div>` : '');
    elements.results.querySelector('#corpusMoreTitles')?.addEventListener('click', () => {
      state.titleOffset = Number(titleInfo.offset || 0) + Number(titleInfo.returned_count || 0);
      runSearch({ appendTitles: true });
    });
    elements.results.querySelectorAll('details[data-source-id]').forEach((details) => {
      details.addEventListener('toggle', () => {
        if (details.open) loadSourceOpening(details);
      });
    });
  }

  async function loadSourceOpening(details) {
    if (details.dataset.loaded || details.dataset.loading) return;
    const sourceId = details.dataset.sourceId;
    if (!sourceId) return;
    details.dataset.loading = '1';
    const target = details.querySelector('.corpus-source-opening');
    if (target) target.textContent = '正在读取该书的篇首原文……';
    try {
      const listing = await requestJson(`/api/reading-harness/chunks?source_id=${encodeURIComponent(sourceId)}&limit=1&offset=0`);
      const first = listing.items?.[0];
      if (!first?.chunk_id) throw new Error('该书没有可展开的切分段落');
      const chunk = await requestJson(`/api/reading-harness/chunk?chunk_id=${encodeURIComponent(first.chunk_id)}`);
      if (target) {
        const lineStart = chunk.reading_line_start || chunk.line_start;
        const lineEnd = chunk.reading_line_end || chunk.line_end;
        target.innerHTML = `<p class="corpus-result-meta">${escapeHtml(chunk.chapter || chunk.source_title || '')} · 行 ${escapeHtml(String(lineStart || '未知'))}-${escapeHtml(String(lineEnd || lineStart || '未知'))} · 字符 ${escapeHtml(String(chunk.reading_start_cp ?? chunk.start_cp ?? '未知'))}-${escapeHtml(String(chunk.reading_end_cp ?? chunk.end_cp ?? '未知'))}</p><pre>${escapeHtml(chunk.context_text || chunk.reading_text || chunk.full_text || '没有可展示的原文。')}</pre>`;
      }
      details.dataset.loaded = '1';
    } catch (error) {
      if (target) target.textContent = `读取失败：${error.message}`;
    } finally {
      delete details.dataset.loading;
    }
  }

  async function loadCorpusSummary() {
    try {
      const result = await requestJson('/api/reading-harness/summary');
      const data = result.data || result;
      const external = Number(data.source_count || 0);
      const chunks = Number(data.chunk_count || 0);
      if (external && chunks) {
        elements.status.textContent = `典籍检索已连接 · 外典 ${external} 种、${chunks} 个切分 · 二王原典检索可用`;
      } else {
        elements.status.textContent = '典籍检索已连接 · 外典统计未提供 · 二王原典检索可用';
      }
    } catch {
      elements.status.textContent = '二王原典检索已就绪 · 外典索引暂不可用';
    }
  }

  async function runSearch({ appendTitles = false } = {}) {
    const query = String(elements.query?.value || '').trim();
    const workKey = elements.work?.value || 'all';
    const mode = selectedMode();
    const collections = selectedCollections();
    if (!query) {
      elements.searchStatus.textContent = '输入书名、篇名或正文片段后检索。';
      elements.resultCount.textContent = '尚未检索';
      elements.results.innerHTML = '';
      return;
    }
    if (!collections.length) {
      state.requestId += 1;
      state.items = [];
      elements.searchStatus.textContent = '未选择任何典籍范围；请选择原典或至少一档外典。';
      elements.resultCount.textContent = '无检索范围';
      elements.results.innerHTML = '<div class="corpus-empty">没有选择检索范围。</div>';
      return;
    }

    if (!appendTitles) {
      state.titleOffset = 0;
      state.items = [];
      state.counts = null;
    }
    const requestId = ++state.requestId;
    elements.searchButton.disabled = true;
    elements.searchStatus.textContent = appendTitles ? '正在读取下一页书名结果……' : '正在搜索所选典籍……';
    elements.results.innerHTML = '<div class="corpus-empty">正在读取检索结果……</div>';
    const address = new URLSearchParams(location.search);
    address.delete('case_id');
    address.set('q', query);
    address.set('mode', mode);
    address.set('work_key', workKey);
    address.delete('collection');
    collections.forEach((collection) => address.append('collection', collection));
    history.replaceState(null, '', '/corpus?' + address);

    try {
      const payload = await requestJson('/api/corpus/unified-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          mode,
          collections,
          work_key: workKey === 'all' ? '' : workKey,
          limit: 8,
          title_offset: state.titleOffset,
        }),
      });
      if (requestId !== state.requestId) return;
      renderResults(payload, { append: appendTitles });
      const countParts = renderCounts(payload.counts);
      const shown = (payload.items || []).length;
      elements.searchStatus.textContent = countParts.length
        ? `${countParts.join('；')}。${appendTitles ? '书名结果已续载。' : ''}`
        : `当前检索没有返回结果；显示 0 条。正文检索未命中不代表全库没有相关材料。`;
      if (shown) elements.status.textContent = `检索完成 · ${collections.map((value) => collectionLabels[value]).join('、')} · ${mode === 'unified' ? '统一模式' : mode === 'body' ? '仅正文' : '仅书名'}`;
    } catch (error) {
      if (requestId !== state.requestId) return;
      elements.results.innerHTML = `<div class="corpus-empty">典籍检索失败：${escapeHtml(error.message)}</div>`;
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
    state.requestId += 1;
    state.titleOffset = 0;
    state.items = [];
    state.counts = null;
    elements.searchButton.disabled = false;
    history.replaceState(null, '', '/corpus');
    elements.query.value = '';
    elements.work.value = 'all';
    document.querySelector('input[name="corpusMode"][value="unified"]').checked = true;
    document.querySelectorAll('input[name="corpusCollection"]').forEach((input) => { input.checked = true; });
    elements.searchStatus.textContent = '全选默认检索二王原典和外典三组；书名命中与正文命中会分别标注。';
    elements.resultCount.textContent = '尚未检索';
    elements.results.innerHTML = '';
  });

  populateWorkFilter();
  loadCorpusSummary();

  async function loadCasePassages(caseId) {
    const requestId = ++state.requestId;
    try {
      const item = await requestJson('/api/v2/case?id=' + encodeURIComponent(caseId));
      const retrieval = await requestJson('/api/corpus/retrieve?case_id=' + encodeURIComponent(caseId))
        .catch(() => ({ items: [], unavailable: true }));
      if (requestId !== state.requestId) return;
      const exact = [
        { passage: item.source_passage, relation: 'source_passage' },
        { passage: item.target_passage, relation: 'target_passage' },
      ].filter(entry => entry.passage).map(({ passage, relation }) => ({
        ...passage,
        kind: 'original_passage',
        collection: 'original',
        collection_label: '二王原典',
        match_scope: 'body',
        match_label: '当前案例已关联原文',
        source_title: passage.document_title || labelForWork(passage.work_key),
        result_id: passage.passage_id,
        location: [passage.document_title, passage.section_title, passage.entry_title].filter(Boolean).join(' · '),
        caseLinked: true,
        matched_text: passage.raw_text,
        passage_text: passage.raw_text,
        related_cases: [{ case_id: caseId, case_title: item.case_title, relations: [relation] }],
      }));
      const seen = new Set(exact.map(passage => passage.passage_id));
      state.items = [];
      renderResults({ items: [...exact, ...(retrieval.items || []).filter(passage => !seen.has(passage.passage_id))] });
      elements.searchStatus.textContent = '当前案例：' + plainTextFromMarkup(item.case_title)
        + (retrieval.unavailable ? '。补充检索暂不可用，已展示关联原文。' : '。已关联原文在前；检索匹配只作补充线索。');
    } catch (error) {
      if (requestId === state.requestId) elements.searchStatus.textContent = '案例原文读取失败：' + error.message;
    }
  }

  const initial = new URLSearchParams(location.search);
  if (initial.has('q')) {
    elements.query.value = initial.get('q');
    if (initial.has('work_key')) elements.work.value = initial.get('work_key');
    if (initial.has('mode')) {
      const mode = document.querySelector(`input[name="corpusMode"][value="${CSS.escape(initial.get('mode'))}"]`);
      if (mode) mode.checked = true;
    }
    if (initial.getAll('collection').length) {
      const selected = new Set(initial.getAll('collection'));
      document.querySelectorAll('input[name="corpusCollection"]').forEach((input) => { input.checked = selected.has(input.value); });
    }
    runSearch();
  } else if (initial.has('case_id')) {
    loadCasePassages(initial.get('case_id'));
  }
})();

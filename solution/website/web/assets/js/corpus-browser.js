(() => {
  const state = {
    requestId: 0,
    titleOffset: 0,
    originalOffset: 0,
    originalLimit: 10,
    items: [],
    counts: null,
    abortController: null,
    savedExternalCollections: null,
  };
  let debounceTimer = 0;
  let isComposing = false;
  const elements = {
    status: document.querySelector('#corpusStatus'),
    resultCount: document.querySelector('#corpusResultCount'),
    form: document.querySelector('#corpusSearchForm'),
    query: document.querySelector('#corpusQuery'),
    allowSingleCharacter: document.querySelector('#corpusAllowSingleCharacter'),
    originalEnabled: document.querySelector('#corpusOriginalEnabled'),
    externalEnabled: document.querySelector('#corpusExternalEnabled'),
    originalRow: document.querySelector('#corpusOriginalRow'),
    externalRow: document.querySelector('#corpusExternalRow'),
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
  const defaultExternalCollections = ['external_high', 'external_mid', 'external_low'];

  function labelForWork(workKey) {
    return workLabels[String(workKey || '')] || String(workKey || '作品未注明');
  }

  function relationLabel(relation) {
    return ({ source_passage: '案例来源段落', target_passage: '案例目标段落', evidence_passage: '案例证据段落' })[relation] || '案例关联段落';
  }

  function selectedMode() {
    return document.querySelector('input[name="corpusMode"]:checked')?.value || 'unified';
  }

  function selectedQueryMatch() {
    return document.querySelector('input[name="corpusQueryMatch"]:checked')?.value || 'all';
  }

  function selectedCollections() {
    return [
      ...(selectedWorkKeys().length ? ['original'] : []),
      ...externalInputs().filter((input) => input.checked).map((input) => input.value),
    ];
  }

  function isSingleHanQuery(value) {
    const normalized = String(value || '').normalize('NFKC').trim();
    return Array.from(normalized).length === 1 && /^\p{Script=Han}$/u.test(normalized);
  }

  function queryTerms(value) {
    const normalized = String(value || '').normalize('NFKC').trim();
    return [...new Set(normalized.split(/[\s,，。；;、？！!?：:/|]+/u).filter(Boolean))].slice(0, 12);
  }

  function containsSingleHanTerm(value) {
    return queryTerms(value).some((term) => isSingleHanQuery(term));
  }

  function workInputs() {
    return [...document.querySelectorAll('input[name="corpusWork"]')];
  }

  function externalInputs() {
    return [...document.querySelectorAll('input[name="corpusCollection"]')];
  }

  function selectedWorkKeys() {
    return workInputs().filter((input) => input.checked).map((input) => input.value);
  }

  function syncOriginalWorkState() {
    const inputs = workInputs();
    const selectedCount = inputs.filter((input) => input.checked).length;
    const allSelected = inputs.length > 0 && selectedCount === inputs.length;
    const anySelected = selectedCount > 0;
    elements.originalEnabled.checked = allSelected;
    elements.originalEnabled.indeterminate = anySelected && !allSelected;
    elements.originalEnabled.setAttribute('aria-checked', anySelected && !allSelected ? 'mixed' : String(allSelected));
    inputs.forEach((input) => { input.disabled = !anySelected; });
    elements.originalRow?.classList.toggle('is-inactive', !anySelected);
  }

  function syncExternalCollectionState() {
    const inputs = externalInputs();
    const selectedCount = inputs.filter((input) => input.checked).length;
    const allSelected = inputs.length > 0 && selectedCount === inputs.length;
    const anySelected = selectedCount > 0;
    const isFrozen = elements.allowSingleCharacter?.checked === true;
    elements.externalEnabled.checked = allSelected;
    elements.externalEnabled.indeterminate = anySelected && !allSelected;
    elements.externalEnabled.setAttribute('aria-checked', anySelected && !allSelected ? 'mixed' : String(allSelected));
    elements.externalEnabled.disabled = isFrozen;
    inputs.forEach((input) => { input.disabled = isFrozen || !anySelected; });
    elements.externalRow?.classList.toggle('is-inactive', !anySelected && !isFrozen);
  }

  function syncSingleCharacterScope({ restoreExternal = true } = {}) {
    const inputs = externalInputs();
    const isEnabled = elements.allowSingleCharacter?.checked === true;
    if (isEnabled) {
      if (state.savedExternalCollections === null) {
        state.savedExternalCollections = inputs.filter((input) => input.checked).map((input) => input.value);
      }
      inputs.forEach((input) => {
        input.checked = false;
        input.disabled = true;
      });
      elements.externalRow?.classList.add('is-frozen');
      elements.externalRow?.setAttribute('aria-disabled', 'true');
    } else {
      if (restoreExternal && state.savedExternalCollections !== null) {
        const restored = new Set(state.savedExternalCollections);
        inputs.forEach((input) => { input.checked = restored.has(input.value); });
      }
      state.savedExternalCollections = null;
      elements.externalRow?.classList.remove('is-frozen');
      elements.externalRow?.removeAttribute('aria-disabled');
    }
    syncExternalCollectionState();
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
    if (!cases.length) return '';
    return `
      <details class="corpus-context-fold corpus-related-block">
        <summary>关联案例（${escapeHtml(String(cases.length))}）</summary>
        <div class="corpus-related-list">
          ${cases.map((caseItem) => `
            <a class="corpus-related-case" href="${escapeHtml(Site.caseUrl('v2', caseItem.case_id))}">
              <span><strong>${escapeHtml(plainTextFromMarkup(caseItem.case_title || '未命名案例'))}</strong><small>${escapeHtml(caseItem.target_work || '目标典籍未明确')} · ${escapeHtml(plainTextFromMarkup(caseItem.target_text || '目标文字未记录'))}</small></span>
              <span class="corpus-related-tags">${(caseItem.relations || []).map((relation) => `<span class="corpus-tag">${escapeHtml(relationLabel(relation))}</span>`).join('')}</span>
            </a>${Site.link(Site.auditUrl(caseItem.case_id), '开始本案释证与审校')}
          `).join('')}
        </div>
      </details>
    `;
  }

  function highlightQueryTerms(value) {
    const text = String(value || '');
    const terms = queryTerms(elements.query?.value)
      .filter((term) => text.includes(term))
      .sort((left, right) => right.length - left.length);
    if (!terms.length) return escapeHtml(text);
    const escapedTerms = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const matcher = new RegExp(`(${escapedTerms.join('|')})`, 'gu');
    const exactTerms = new Set(terms);
    return text.split(matcher).map((part) => exactTerms.has(part)
      ? `<mark class="match-mark">${escapeHtml(part)}</mark>`
      : escapeHtml(part)).join('');
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
    const safeMatchedText = highlightQueryTerms(matchedText);
    const queryTermCount = queryTerms(elements.query?.value).length;
    const matchedTerms = Array.isArray(item.matched_terms)
      ? item.matched_terms
      : queryTerms(elements.query?.value).filter((term) => matchedText.includes(term));
    const matchedTermsMeta = queryTermCount > 1 && matchedTerms.length
      ? [`本条命中：${matchedTerms.join('、')}`]
      : [];
    const matchText = kind === 'external_source'
      ? `<p class="corpus-result-text corpus-title-match">书名或路径包含：${escapeHtml(matchedText || sourceTitle)}</p>`
      : `<p class="corpus-result-text">${safeMatchedText || '没有可展示的命中文段。'}</p>`;

    const resultNumber = index + 1;
    const resultAnchor = kind === 'original_passage' ? `corpus-result-${resultNumber}` : '';
    const resultRank = resultAnchor
      ? `<a class="corpus-rank corpus-rank-link" href="#${resultAnchor}" aria-label="定位到第 ${resultNumber} 条">${resultNumber}</a>`
      : `<span class="corpus-rank">${resultNumber}</span>`;

    return `
      <article class="corpus-result"${resultAnchor ? ` id="${resultAnchor}"` : ''}>
        <div class="corpus-detail-topline">
          <div class="corpus-result-title">
            ${resultRank}
            <span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(collectionLabel)} · ${escapeHtml(location)}</small></span>
          </div>
          <span class="corpus-status-chip">${escapeHtml(label)}</span>
        </div>
        ${matchText}
        <p class="corpus-result-meta">${[...meta, ...matchedTermsMeta].map((value) => escapeHtml(String(value))).join(' · ')}</p>
        ${expansion}
        ${relatedCases.length ? renderRelatedCases(relatedCases) : ''}
      </article>
    `;
  }

  function renderCounts(counts) {
    const parts = [];
    if (counts?.original?.candidate_count_capped) parts.push(`原典候选至少 ${counts.original.candidate_count} 段；分页范围为前 500 段`);
    if (counts?.external_body?.returned_count) {
      parts.push(`外典候选 ${counts.external_body.candidate_count} 段`);
    }
    if (counts?.external_title?.total) {
      parts.push(`书名/路径 ${counts.external_title.total} 项`);
    }
    return parts;
  }

  function renderResults(payload, { append = false } = {}) {
    const items = Array.isArray(payload?.items) ? payload.items : [];
    state.items = stableItems(items, append);
    state.counts = payload?.counts || null;
    const originalPage = state.counts?.original;
    const originalTotal = Number(originalPage?.result_count || 0);
    const originalOffset = Number(originalPage?.offset || 0);
    const originalReturned = Number(originalPage?.returned_count || 0);
    state.originalOffset = originalOffset;
    elements.resultCount.textContent = originalReturned
      ? `显示 ${originalOffset + 1}–${originalOffset + originalReturned} / ${originalPage?.candidate_count_capped ? `当前 ${originalTotal}` : `共 ${originalTotal}`} 段`
      : state.items.length ? `显示 ${state.items.length} 条` : '没有结果';
    if (!state.items.length) {
      elements.results.innerHTML = '<div class="corpus-empty">未找到匹配项。外典结果仅为字面线索，未命中不代表没有相关材料。</div>';
      return;
    }

    const rendered = state.items.map((item, index) => renderItem(item, originalOffset + index)).join('');
    const titleInfo = state.counts?.external_title;
    const titleHasMore = titleInfo && Number(titleInfo.offset || 0) + Number(titleInfo.returned_count || 0) < Number(titleInfo.total || 0);
    const pageSize = Math.max(1, Number(originalPage?.limit || state.originalLimit));
    const pageNumber = Math.floor(originalOffset / pageSize) + 1;
    const pageCount = Math.max(1, Math.ceil(originalTotal / pageSize));
    const hasPreviousOriginalPage = originalOffset > 0;
    const hasNextOriginalPage = originalOffset + originalReturned < originalTotal;
    const originalPagination = originalTotal > pageSize ? `<nav class="corpus-more-actions corpus-pagination" aria-label="原典结果分页"><button class="corpus-previous-original-page search-clear toolbar-button" type="button"${hasPreviousOriginalPage ? '' : ' disabled'}>上一页</button><span>第 ${pageNumber}/${pageCount} 页 · 每页 ${pageSize} 段</span><button class="corpus-next-original-page search-clear toolbar-button" type="button"${hasNextOriginalPage ? '' : ' disabled'}>下一页</button><label class="corpus-page-jump">跳至<input class="corpus-page-number" type="number" min="1" max="${pageCount}" value="${pageNumber}" aria-label="跳转到第几页" />/${pageCount} 页</label><button class="corpus-page-jump-button search-clear toolbar-button" type="button">跳转</button></nav>` : '';
    const moreTitlesButton = titleHasMore
      ? `<button id="corpusMoreTitles" class="search-clear toolbar-button" type="button">加载更多书名结果（${escapeHtml(String(Math.max(0, Number(titleInfo.total) - Number(titleInfo.offset) - Number(titleInfo.returned_count))))} 项）</button>`
      : '';
    elements.results.innerHTML = rendered + originalPagination + (moreTitlesButton ? `<div class="corpus-more-actions">${moreTitlesButton}</div>` : '');
    const pageAnchor = location.hash.slice(1);
    const anchorTarget = pageAnchor ? document.getElementById(pageAnchor) : null;
    const currentQuery = String(elements.query?.value || '').trim();
    if (currentQuery) updateSearchAddress(currentQuery, { preserveHash: Boolean(anchorTarget) });
    if (anchorTarget) window.requestAnimationFrame(() => anchorTarget.scrollIntoView({ block: 'start' }));
    elements.results.querySelectorAll('.corpus-previous-original-page').forEach((button) => {
      button.addEventListener('click', () => {
        state.originalOffset = Math.max(0, originalOffset - pageSize);
        runSearch({ pageOriginal: true });
      });
    });
    elements.results.querySelectorAll('.corpus-next-original-page').forEach((button) => {
      button.addEventListener('click', () => {
        state.originalOffset = originalOffset + pageSize;
        runSearch({ pageOriginal: true });
      });
    });
    const pageInput = elements.results.querySelector('.corpus-page-number');
    const jumpToPage = () => {
      const requestedPage = Number(pageInput?.value);
      if (!Number.isInteger(requestedPage) || !pageInput) return;
      const targetPage = Math.min(pageCount, Math.max(1, requestedPage));
      pageInput.value = String(targetPage);
      state.originalOffset = (targetPage - 1) * pageSize;
      runSearch({ pageOriginal: true });
    };
    elements.results.querySelector('.corpus-page-jump-button')?.addEventListener('click', jumpToPage);
    pageInput?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        jumpToPage();
      }
    });
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

  function updateSearchAddress(query, { preserveHash = false } = {}) {
    const address = new URLSearchParams(location.search);
    address.delete('case_id');
    address.delete('q');
    if (query) address.set('q', query);
    address.set('mode', selectedMode());
    address.set('match', selectedQueryMatch());
    address.set('scope_set', '1');
    address.delete('work_key');
    selectedWorkKeys().forEach((workKey) => address.append('work_key', workKey));
    address.set('page', String(Math.floor(state.originalOffset / state.originalLimit) + 1));
    address.delete('original_offset');
    if (elements.allowSingleCharacter?.checked) address.set('single_char', '1');
    else address.delete('single_char');
    address.delete('collection');
    selectedCollections().forEach((collection) => address.append('collection', collection));
    const queryString = address.toString();
    const hash = preserveHash ? location.hash : '';
    history.replaceState(null, '', `${queryString ? `/corpus?${queryString}` : '/corpus'}${hash}`);
  }

  function searchValidation(query) {
    if (!query) return { message: '', count: '尚未检索' };
    const terms = queryTerms(query);
    const hasSingleHanTerm = terms.some((term) => isSingleHanQuery(term));
    if (hasSingleHanTerm && !elements.allowSingleCharacter.checked) {
      return { message: '检索词包含单字；勾选“允许单字词检索”后可查二王原典。', count: '单字词检索未开启' };
    }
    if (!terms.some((term) => Array.from(term).length >= 2 || isSingleHanQuery(term))) {
      return { message: '默认检索至少两个字符。', count: '请输入检索词' };
    }
    const collections = selectedCollections();
    if (hasSingleHanTerm && !collections.includes('original')) {
      return { message: '单字词检索需勾选至少一部二王原典。', count: '请选择二王原典' };
    }
    if (!collections.length) {
      return { message: '请至少选择一类典籍范围。', count: '无检索范围' };
    }
    return null;
  }

  function cancelPendingSearch() {
    if (debounceTimer) window.clearTimeout(debounceTimer);
    debounceTimer = 0;
    state.abortController?.abort();
    state.abortController = null;
    state.requestId += 1;
  }

  function clearSearchResults(message = '', count = '尚未检索') {
    state.titleOffset = 0;
    state.originalOffset = 0;
    state.items = [];
    state.counts = null;
    elements.searchStatus.textContent = message;
    elements.resultCount.textContent = count;
    elements.results.innerHTML = '';
  }

  function scheduleSearch({ delay = 350 } = {}) {
    cancelPendingSearch();
    state.titleOffset = 0;
    state.originalOffset = 0;
    state.items = [];
    state.counts = null;
    const query = String(elements.query?.value || '').trim();
    updateSearchAddress(query);
    if (!query) {
      clearSearchResults();
      return;
    }
    const validation = searchValidation(query);
    if (validation) {
      clearSearchResults(validation.message, validation.count);
      return;
    }
    const requestId = state.requestId;
    elements.searchStatus.textContent = '正在等待检索……';
    elements.resultCount.textContent = '正在检索';
    elements.results.innerHTML = '<div class="corpus-empty">正在检索……</div>';
    debounceTimer = window.setTimeout(() => {
      if (requestId !== state.requestId) return;
      debounceTimer = 0;
      runSearch();
    }, delay);
  }

  async function runSearch({ appendTitles = false, pageOriginal = false, preserveHash = false } = {}) {
    if (debounceTimer) window.clearTimeout(debounceTimer);
    debounceTimer = 0;
    state.abortController?.abort();
    state.abortController = null;
    const requestId = ++state.requestId;
    const query = String(elements.query?.value || '').trim();
    const workKeys = selectedWorkKeys();
    const mode = selectedMode();
    const queryMatch = selectedQueryMatch();
    const selectedCollectionValues = selectedCollections();
    const hasSingleHanTerm = containsSingleHanTerm(query);
    const allowSingleCharacter = elements.allowSingleCharacter?.checked === true;
    const validation = searchValidation(query);
    if (validation) {
      if (!appendTitles) clearSearchResults(validation.message, validation.count);
      return;
    }
    const collections = hasSingleHanTerm ? ['original'] : selectedCollectionValues;

    if (!appendTitles) {
      if (!pageOriginal) {
        state.titleOffset = 0;
        state.originalOffset = 0;
      }
      state.items = [];
      state.counts = null;
    }
    updateSearchAddress(query, { preserveHash });
    const controller = new AbortController();
    state.abortController = controller;
    elements.searchStatus.textContent = appendTitles ? '正在读取下一页书名结果……' : '正在搜索所选典籍……';
    elements.results.innerHTML = '<div class="corpus-empty">正在读取检索结果……</div>';

    try {
      const payload = await requestJson('/api/corpus/unified-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          query,
          mode,
          query_match: queryMatch,
          collections,
          work_key: workKeys.length === 1 ? workKeys[0] : '',
          work_keys: workKeys,
          allow_single_character: allowSingleCharacter,
          limit: state.originalLimit,
          original_offset: state.originalOffset,
          title_offset: state.titleOffset,
        }),
      });
      if (requestId !== state.requestId) return;
      renderResults(payload, { append: appendTitles });
      const countParts = renderCounts(payload.counts);
      elements.searchStatus.textContent = countParts.length
        ? countParts.join('；')
        : (payload.items || []).length ? '' : '未找到匹配项。';
    } catch (error) {
      if (requestId !== state.requestId || error.name === 'AbortError') return;
      elements.results.innerHTML = `<div class="corpus-empty">典籍检索失败：${escapeHtml(error.message)}</div>`;
      elements.searchStatus.textContent = '检索失败，请稍后重试。';
      elements.resultCount.textContent = '检索失败';
    } finally {
      if (requestId === state.requestId) state.abortController = null;
    }
  }

  elements.query?.addEventListener('compositionstart', () => {
    isComposing = true;
    cancelPendingSearch();
    clearSearchResults();
  });
  elements.query?.addEventListener('compositionend', () => {
    isComposing = false;
    scheduleSearch();
  });
  elements.query?.addEventListener('input', () => {
    if (!isComposing) scheduleSearch();
  });
  elements.form?.addEventListener('submit', (event) => {
    event.preventDefault();
    scheduleSearch({ delay: 0 });
  });
  elements.allowSingleCharacter?.addEventListener('change', () => {
    syncSingleCharacterScope();
    scheduleSearch({ delay: 100 });
  });
  elements.originalEnabled?.addEventListener('change', () => {
    const selectAll = elements.originalEnabled.checked;
    workInputs().forEach((input) => { input.checked = selectAll; });
    syncOriginalWorkState();
    scheduleSearch({ delay: 100 });
  });
  elements.externalEnabled?.addEventListener('change', () => {
    const selectAll = elements.externalEnabled.checked;
    externalInputs().forEach((input) => { input.checked = selectAll; });
    syncExternalCollectionState();
    scheduleSearch({ delay: 100 });
  });
  workInputs().forEach((input) => input.addEventListener('change', () => {
    syncOriginalWorkState();
    scheduleSearch({ delay: 100 });
  }));
  externalInputs().forEach((input) => input.addEventListener('change', () => {
    syncExternalCollectionState();
    scheduleSearch({ delay: 100 });
  }));
  document.querySelectorAll('input[name="corpusMode"]').forEach((input) => input.addEventListener('change', () => scheduleSearch({ delay: 100 })));
  document.querySelectorAll('input[name="corpusQueryMatch"]').forEach((input) => input.addEventListener('change', () => scheduleSearch({ delay: 100 })));
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
  const initialWorkKeys = [...new Set(initial.getAll('work_key').filter((workKey) => workLabels[workKey]))];
  const initialCollections = initial.getAll('collection');
  const hasInitialScope = initial.get('scope_set') === '1' || initialCollections.length > 0;
  const initialSingleCharacter = initial.get('single_char') === '1';
  const initialPageValue = Number(initial.get('page'));
  const initialPage = Number.isInteger(initialPageValue) && initialPageValue > 0 ? initialPageValue : 0;
  const resultAnchorMatch = /^corpus-result-(\d+)$/.exec(location.hash.slice(1));
  const anchoredResultNumber = resultAnchorMatch ? Number(resultAnchorMatch[1]) : 0;
  if (initial.has('q')) elements.query.value = initial.get('q');
  if (initial.has('mode')) {
    const mode = document.querySelector(`input[name="corpusMode"][value="${CSS.escape(initial.get('mode'))}"]`);
    if (mode) mode.checked = true;
  }
  if (initial.has('match')) {
    const queryMatch = document.querySelector(`input[name="corpusQueryMatch"][value="${CSS.escape(initial.get('match'))}"]`);
    if (queryMatch) queryMatch.checked = true;
  }
  if (hasInitialScope) {
    const selectedCollectionsFromUrl = new Set(initialCollections);
    const includeOriginal = selectedCollectionsFromUrl.has('original');
    const useAllOriginalWorks = includeOriginal && (!initialWorkKeys.length || initialWorkKeys.includes('all'));
    workInputs().forEach((input) => {
      input.checked = includeOriginal && (useAllOriginalWorks || initialWorkKeys.includes(input.value));
    });
    externalInputs().forEach((input) => { input.checked = selectedCollectionsFromUrl.has(input.value); });
  } else if (initialWorkKeys.length && !initialWorkKeys.includes('all')) {
    workInputs().forEach((input) => { input.checked = initialWorkKeys.includes(input.value); });
  }
  elements.allowSingleCharacter.checked = initialSingleCharacter;
  if (initialSingleCharacter && !externalInputs().some((input) => input.checked)) {
    state.savedExternalCollections = [...defaultExternalCollections];
  }
  syncOriginalWorkState();
  syncSingleCharacterScope({ restoreExternal: false });
  loadCorpusSummary();

  const initialQuery = String(elements.query?.value || '').trim();
  if (initialQuery) {
    const initialOriginalOffset = Number(initial.get('original_offset') || 0);
    if (initialPage) {
      state.originalOffset = Math.min((initialPage - 1) * state.originalLimit, 100000);
    } else if (anchoredResultNumber > 0) {
      const anchorPage = Math.floor((anchoredResultNumber - 1) / state.originalLimit) + 1;
      state.originalOffset = Math.min((anchorPage - 1) * state.originalLimit, 100000);
    } else {
      state.originalOffset = Number.isInteger(initialOriginalOffset) && initialOriginalOffset > 0
        ? Math.min(initialOriginalOffset, 100000) : 0;
    }
    runSearch({ pageOriginal: true, preserveHash: anchoredResultNumber > 0 });
  } else if (initial.has('case_id')) {
    loadCasePassages(initial.get('case_id'));
  }
})();

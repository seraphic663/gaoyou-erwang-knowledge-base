(() => {
  const pageSize = 10;
  const workLabels = {
    dushu_zazhi: '《读书杂志》',
    guangya_shuzheng: '《广雅疏证》',
    jingyi_shuwen: '《经义述闻》',
    jingzhuan_shici: '《经传释词》',
  };
  const state = {
    requestId: 0,
    timer: 0,
    abortController: null,
    meta: null,
    composing: false,
    currentPage: 1,
    totalPages: 1,
  };
  const elements = {
    root: document.querySelector('#machineLibrary'),
    form: document.querySelector('#machineSearchForm'),
    query: document.querySelector('#machineQuery'),
    masterWork: document.querySelector('#machineOriginalEnabled'),
    works: [...document.querySelectorAll('input[name="machineWork"]')],
    relationType: document.querySelector('#machineRelationType'),
    position: document.querySelector('#machinePosition'),
    positionHelp: document.querySelector('#machinePositionHelp'),
    match: document.querySelector('#machineMatch'),
    viewButtons: [...document.querySelectorAll('[data-machine-view]')],
    runStatus: document.querySelector('#machineRunStatus'),
    searchStatus: document.querySelector('#machineSearchStatus'),
    summary: document.querySelector('#machineResultSummary'),
    results: document.querySelector('#machineResults'),
    mentions: document.querySelector('#machineMentions'),
    mentionList: document.querySelector('#machineMentionList'),
    unsegmented: document.querySelector('#machineUnsegmented'),
    unsegmentedList: document.querySelector('#machineUnsegmentedList'),
    suppressed: document.querySelector('#machineSuppressed'),
    suppressedList: document.querySelector('#machineSuppressedList'),
    pager: document.querySelector('#machinePager'),
    previous: document.querySelector('#machinePreviousPage'),
    next: document.querySelector('#machineNextPage'),
    pageInput: document.querySelector('#machinePageInput'),
    jumpPage: document.querySelector('#machineJumpPage'),
    pageSummary: document.querySelector('#machinePageSummary'),
    runDetails: document.querySelector('#machineRunDetails'),
  };

  if (!elements.root) return;

  function text(value) {
    return String(value ?? '');
  }

  function escape(value) {
    return escapeHtml(text(value));
  }

  function tokens(value) {
    return text(value).trim().split(/\s+/u).filter(Boolean);
  }

  function anchorId(prefix, value) {
    const encoded = Array.from(text(value)).map((character) => {
      return /^[a-zA-Z0-9_-]$/.test(character)
        ? character
        : `_u${character.codePointAt(0).toString(16)}_`;
    }).join('');
    return `${prefix}-${encoded || 'item'}`;
  }

  function activeView() {
    return elements.viewButtons.find((button) => button.getAttribute('aria-pressed') === 'true')?.dataset.machineView || 'terms';
  }

  function setView(view) {
    const normalized = view === 'cases' ? 'cases' : 'terms';
    for (const button of elements.viewButtons) {
      button.setAttribute('aria-pressed', String(button.dataset.machineView === normalized));
    }
  }

  function selectedWorkKeys() {
    return elements.works.filter((input) => input.checked).map((input) => input.value);
  }

  function syncMasterWork() {
    const selected = selectedWorkKeys().length;
    elements.masterWork.checked = selected === elements.works.length;
    elements.masterWork.indeterminate = selected > 0 && selected < elements.works.length;
  }

  function selectedType() {
    return elements.relationType.value || '';
  }

  function currentState(page = state.currentPage) {
    const workKeys = selectedWorkKeys();
    return {
      q: text(elements.query.value).trim(),
      view: activeView(),
      match: elements.match.value === 'any' ? 'any' : 'all',
      position: elements.position.value,
      workKeys: workKeys.length ? workKeys : ['none'],
      type: selectedType(),
      page: Math.max(1, Number(page) || 1),
      pageSize,
    };
  }

  function urlFor(searchState) {
    const params = new URLSearchParams();
    if (searchState.q) params.set('q', searchState.q);
    params.set('view', searchState.view);
    params.set('match', searchState.match);
    if (searchState.position !== 'any') params.set('position', searchState.position);
    for (const key of searchState.workKeys) params.append('work_key', key);
    if (searchState.type) params.set('type', searchState.type);
    params.set('page', String(searchState.page));
    return `${location.pathname}${params.size ? `?${params.toString()}` : ''}`;
  }

  function writeHistory(searchState, mode = 'push') {
    const nextUrl = urlFor(searchState);
    const currentUrl = `${location.pathname}${location.search}`;
    if (nextUrl === currentUrl) return;
    if (mode === 'replace') history.replaceState({ machineLibrary: true }, '', nextUrl);
    else history.pushState({ machineLibrary: true }, '', nextUrl);
  }

  function restoreFromUrl() {
    const params = new URLSearchParams(location.search);
    const query = params.get('q') || '';
    elements.query.value = query;

    const requestedView = params.get('view');
    const pathDefault = location.pathname === '/cases' ? 'cases' : 'terms';
    setView(requestedView === 'terms' || requestedView === 'cases' ? requestedView : pathDefault);

    elements.match.value = params.get('match') === 'any' ? 'any' : 'all';
    elements.position.value = ['source', 'target'].includes(params.get('position')) ? params.get('position') : 'any';
    elements.positionHelp.hidden = elements.position.value === 'any';
    const workKeys = params.getAll('work_key');
    if (!workKeys.length) {
      elements.works.forEach((input) => { input.checked = true; });
    } else {
      const selected = new Set(workKeys.filter((value) => value !== 'none'));
      elements.works.forEach((input) => { input.checked = selected.has(input.value); });
    }
    syncMasterWork();

    const requestedType = params.get('type') || '';
    if (requestedType && ![...elements.relationType.options].some((option) => option.value === requestedType)) {
      const option = document.createElement('option');
      option.value = requestedType;
      option.textContent = requestedType;
      elements.relationType.append(option);
    }
    elements.relationType.value = requestedType;

    const requestedPage = Number(params.get('page'));
    state.currentPage = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
    elements.pageInput.value = String(state.currentPage);
  }

  function searchParamsFor(searchState) {
    const params = new URLSearchParams();
    params.set('q', searchState.q);
    params.set('view', searchState.view);
    params.set('match', searchState.match);
    params.set('position', searchState.position);
    for (const key of searchState.workKeys) params.append('work_key', key);
    if (searchState.type) params.set('type', searchState.type);
    params.set('page', String(searchState.page));
    params.set('page_size', String(pageSize));
    params.set('include_mentions', '1');
    return params;
  }

  function cancelPending() {
    if (state.timer) window.clearTimeout(state.timer);
    state.timer = 0;
    state.abortController?.abort();
    state.abortController = null;
    state.requestId += 1;
  }

  function showLoading() {
    elements.searchStatus.textContent = '正在检索……';
    elements.summary.textContent = '正在读取结果。';
    elements.results.innerHTML = '<div class="ml-empty">正在检索……</div>';
    elements.mentions.hidden = true;
    elements.mentionList.replaceChildren();
    elements.unsegmented.hidden = true;
    elements.unsegmentedList.replaceChildren();
    elements.suppressed.hidden = true;
    elements.suppressedList.replaceChildren();
    elements.pager.hidden = true;
  }

  function scheduleSearch() {
    if (state.composing) return;
    cancelPending();
    state.currentPage = 1;
    const requestId = state.requestId;
    state.timer = window.setTimeout(() => {
      if (requestId !== state.requestId) return;
      state.timer = 0;
      runSearch({ historyMode: 'push', page: 1 });
    }, 350);
    showLoading();
  }

  function relationTypeName(type, label) {
    const raw = text(type);
    const known = {
      gloss: '训释',
      reading: '读法',
      loan: '通假',
      emendation: '校勘',
      emendation_phrase: '短语校勘',
    };
    return known[raw] || text(label).replace(/候[选選]/g, '') || raw || '关系类型未标明';
  }

  function directionArrow(directionality) {
    return directionality === 'symmetric' ? '↔' : '→';
  }

  function querySide(item, searchState, leftForm = item?.left_form, rightForm = item?.right_form) {
    const explicit = text(item?.query_side).toLowerCase();
    if (['left', 'right', 'both'].includes(explicit)) return explicit;
    const queryTokens = tokens(searchState.q);
    const left = text(leftForm);
    const right = text(rightForm);
    const leftHas = queryTokens.some((token) => left.includes(token));
    const rightHas = queryTokens.some((token) => right.includes(token));
    if (leftHas && rightHas) return 'both';
    if (leftHas) return 'left';
    if (rightHas) return 'right';
    return '';
  }

  function sideLabel(side, directionality) {
    if (directionality === 'symmetric') return side ? '双向关系命中' : '';
    return ({ left: '原词／原句命中', right: '释义／异文命中', both: '两端命中' })[side] || '';
  }

  function relationCues(item) {
    const raw = item?.relation_cues ?? item?.cues ?? item?.relation_cue ?? item?.cue
      ?? (Array.isArray(item?.claim_cues) ? item.claim_cues.map((value) => value?.relation_cue) : null);
    if (Array.isArray(raw)) return [...new Set(raw.map((value) => text(typeof value === 'object' ? value?.relation_cue || value?.cue : value).trim()).filter(Boolean))];
    return raw ? [text(raw).trim()] : [];
  }

  function stanceLabel(value) {
    return ({
      asserted: '原文直陈',
      proposed: '存疑说法',
      reported: '转述观点',
      uncertain: '立场未定',
      rejected: '否定观点',
      conditional: '条件说法',
    })[text(value)] || '';
  }

  function claimCueDetails(item) {
    const claims = Array.isArray(item?.claim_cues) ? item.claim_cues : [];
    if (!claims.length) return '';
    return `<details class="ml-claim-variants"><summary>各来源主张原方向与措辞（${claims.length}）</summary><ul>${claims.map((claim) => {
      const left = relationFormMarkup(claim?.left_form, '左');
      const right = relationFormMarkup(claim?.right_form, '右');
      const arrow = directionArrow(claim?.directionality);
      const cue = text(claim?.relation_cue);
      const stance = stanceLabel(claim?.author_stance);
      return `<li><strong>${left} ${arrow} ${right}</strong>${cue ? ` · 原文措辞：${escape(cue)}` : ''}${stance ? ` · ${escape(stance)}` : ''}</li>`;
    }).join('')}</ul></details>`;
  }

  function compareQuerySide(left, right) {
    const rank = { left: 0, both: 1, right: 2, '': 3 };
    return (rank[left] ?? 3) - (rank[right] ?? 3);
  }

  function sortedTerms(items, searchState) {
    return [...items].sort((left, right) => compareQuerySide(
      querySide(left, searchState),
      querySide(right, searchState),
    ));
  }

  function sortedRelations(items, searchState) {
    return [...items].sort((left, right) => compareQuerySide(
      querySide(left, searchState),
      querySide(right, searchState),
    ));
  }

  function workTitle(workKey, suppliedTitle = '') {
    return text(suppliedTitle) || workLabels[text(workKey)] || text(workKey) || '来源原典未注明';
  }

  function locationLabel(item) {
    return text(item?.location || item?.chapter || item?.section_title || item?.passage_id || '位置未注明');
  }

  function quoteMarkup(quote) {
    return quote ? `<blockquote class="ml-quote">${escape(quote)}</blockquote>` : '<p class="ml-card-meta">当前记录未返回案例引文。</p>';
  }

  function relationFormText(value, side) {
    if (value === null || value === undefined) return `（${side}端未提供）`;
    return String(value) === '' ? '∅' : String(value);
  }

  function relationFormMarkup(value, side) {
    const display = relationFormText(value, side);
    const emptyForm = value !== null && value !== undefined && String(value) === '';
    const attributes = emptyForm ? ' title="此处无字" aria-label="此处无字"' : '';
    return `<span${attributes}>${escape(display)}</span>`;
  }

  function detailFold(id) {
    if (!id) return '';
    return `<details class="ml-context-fold" data-machine-detail-id="${escape(id)}"><summary>展开原文与邻接上下文</summary><div class="ml-detail-content">展开后按需读取。</div></details>`;
  }

  function detailMarkup(payload) {
    if (payload?.available === false || payload?.found === false) return '<p>未找到可展开的原文。</p>';
    const source = payload?.source || {};
    const context = payload?.context || {};
    const point = payload?.proofreading_point || {};
    const location = text(source.location || point.location);
    const trigger = text(point.trigger);
    const before = text(context.before);
    const focus = text(context.focus);
    const after = text(context.after);
    const rawText = text(source.raw_text || source.plain_text);
    const claims = Array.isArray(payload?.claims) ? payload.claims : [];
    const span = point.issue_start_cp !== undefined && point.issue_end_cp !== undefined
      ? `字符 ${point.issue_start_cp}–${point.issue_end_cp}`
      : '';
    const contextText = before || focus || after
      ? `<pre class="ml-context-text">${escape(before)}${focus ? `<mark>${escape(focus)}</mark>` : ''}${escape(after)}</pre>`
      : rawText ? `<pre class="ml-context-text">${escape(rawText)}</pre>` : '<p>接口未返回原文片段。</p>';
    const fullText = rawText && (before || focus || after)
      ? `<details class="ml-full-source"><summary>展开完整原文段</summary><pre class="ml-context-text">${escape(rawText)}</pre></details>`
      : '';
    const claimDetails = claims.length ? `<details class="ml-full-source"><summary>各来源关系主张（${claims.length}）</summary><ul>${claims.map((claim) => {
      const left = relationFormMarkup(claim?.left_form, '左');
      const right = relationFormMarkup(claim?.right_form, '右');
      const cue = text(claim?.relation_cue);
      const stance = stanceLabel(claim?.author_stance);
      const quote = text(claim?.quote);
      return `<li><strong>${left} ${directionArrow(claim?.directionality)} ${right}</strong>${cue || stance ? `<p>${cue ? `原文措辞：${escape(cue)}` : ''}${cue && stance ? ' · ' : ''}${stance ? escape(stance) : ''}</p>` : ''}${quote ? `<blockquote class="ml-quote">${escape(quote)}</blockquote>` : ''}</li>`;
    }).join('')}</ul></details>` : '';
    const meta = [location, span, trigger ? `原文措辞：${trigger}` : ''].filter(Boolean).join(' · ');
    return `${meta ? `<p class="ml-detail-meta">${escape(meta)}</p>` : ''}${contextText}${claimDetails}${fullText}`;
  }

  async function loadDetail(details) {
    if (details.dataset.loaded || details.dataset.loading) return;
    const id = details.dataset.machineDetailId;
    const content = details.querySelector('.ml-detail-content');
    if (!id || !content) return;
    details.dataset.loading = '1';
    content.textContent = '正在读取原文……';
    try {
      const params = new URLSearchParams({ id });
      const payload = await requestJson(`/api/machine/detail?${params.toString()}`);
      content.innerHTML = detailMarkup(payload);
      details.dataset.loaded = '1';
    } catch {
      content.textContent = '原文暂不可读取，请稍后重试。';
    } finally {
      delete details.dataset.loading;
    }
  }

  function attachLazyDetails(container) {
    container.querySelectorAll('details[data-machine-detail-id]').forEach((details) => {
      details.addEventListener('toggle', () => {
        if (details.open) loadDetail(details);
      });
    });
  }

  function claimIds(item) {
    const ids = Array.isArray(item?.claim_ids) ? item.claim_ids : [];
    return [...new Set(ids.map((id) => text(id)).filter(Boolean))];
  }

  function renderRelationLine(item, searchState, { compact = false } = {}) {
    const leftRaw = item?.left_form;
    const rightRaw = item?.right_form;
    const side = querySide(item, searchState, leftRaw, rightRaw);
    const left = relationFormMarkup(leftRaw, '左');
    const right = relationFormMarkup(rightRaw, '右');
    const relationType = text(item?.relation_type);
    const relationLabel = relationTypeName(relationType, item?.relation_label);
    const arrow = directionArrow(item?.directionality);
    const ids = claimIds(item);
    const cues = relationCues(item);
    const stance = stanceLabel(item?.author_stance);
    const sizeClass = compact ? ' ml-relation-compact' : '';
    return `
      <div class="ml-relation-row${sizeClass}">
        <div class="ml-relation-line">
          <span class="ml-type-badge">${escape(relationLabel)}</span>
          <strong class="ml-relation-form">${left} <span class="ml-arrow" aria-label="${arrow === '↔' ? '对称关系' : '原文关系叙述方向'}">${arrow}</span> ${right}</strong>
          ${side ? `<span class="ml-side-badge">${sideLabel(side, item?.directionality)}</span>` : ''}
          ${stance ? `<span class="ml-side-badge">${escape(stance)}</span>` : ''}
        </div>
        ${cues.length ? `<p class="ml-cue">原文关系措辞：${cues.map(escape).join('、')}</p>` : ''}
        ${claimCueDetails(item)}
        ${ids.length ? `<span class="ml-claim-count">${ids.length} 条命中关系主张</span>` : ''}
      </div>
    `;
  }

  function renderTermCase(item, index, relationId) {
    const id = text(item?.id || item?.passage_id || `${relationId}-${index + 1}`);
    const domId = anchorId('ml-case-source', `${relationId}-${id}`);
    const title = workTitle(item?.work_key, item?.work_title);
    const location = locationLabel(item);
    return `
      <li class="ml-case-item" id="${escape(domId)}">
        <div class="ml-case-title"><strong>${escape(title)}</strong><span>${escape(location)}</span></div>
        ${quoteMarkup(item?.quote)}
        ${detailFold(id)}
      </li>
    `;
  }

  function renderTermCard(item, index, searchState) {
    const claims = claimIds(item);
    const stableKey = text(item?.id || claims[0] || `${item?.left_form || ''}-${item?.right_form || ''}-${index}`);
    const id = anchorId('ml-relation-card', stableKey);
    const leftRaw = item?.left_form;
    const rightRaw = item?.right_form;
    const side = querySide(item, searchState, leftRaw, rightRaw);
    const left = relationFormMarkup(leftRaw, '左');
    const right = relationFormMarkup(rightRaw, '右');
    const relationLabel = relationTypeName(item?.relation_type, item?.relation_label);
    const cues = relationCues(item);
    const stance = stanceLabel(item?.author_stance);
    const cases = Array.isArray(item?.cases) ? item.cases : [];
    const visibleCases = cases.slice(0, 3);
    const hiddenCases = cases.slice(3);
    const countText = `${cases.length} 个关联案例${claims.length ? ` · ${claims.length} 条命中主张` : ''}`;
    const caseMarkup = visibleCases.map((caseItem, caseIndex) => renderTermCase(caseItem, caseIndex, stableKey)).join('');
    const hiddenCaseMarkup = hiddenCases.length ? `
      <details class="ml-more-cases">
        <summary>展开其余 ${hiddenCases.length} 个关联案例</summary>
        <ol class="ml-case-list">${hiddenCases.map((caseItem, caseIndex) => renderTermCase(caseItem, caseIndex + 3, stableKey)).join('')}</ol>
      </details>
    ` : '';
    return `
      <article class="ml-card ml-term-card" id="${escape(id)}">
        <header class="ml-card-head">
          <div class="ml-card-main">
            <p class="ml-card-kicker">字词关系 · ${escape(relationLabel)}</p>
            <h2 class="ml-relation-form">${left} <span class="ml-arrow" aria-label="${item?.directionality === 'symmetric' ? '对称关系' : '原文关系叙述方向'}">${directionArrow(item?.directionality)}</span> ${right}</h2>
            <div class="ml-relation-meta">
              ${side ? `<span class="ml-side-badge">${sideLabel(side, item?.directionality)}</span>` : ''}
              ${stance ? `<span class="ml-side-badge">${escape(stance)}</span>` : ''}
              <span class="ml-claim-count">${escape(countText)}</span>
            </div>
            ${cues.length ? `<p class="ml-cue">原文关系措辞：${cues.map(escape).join('、')}</p>` : ''}
            ${claimCueDetails(item)}
            <div class="ml-card-tools"><a href="#${escape(id)}">定位此关系卡</a></div>
          </div>
          <span class="ml-machine-badge">机器候选 · 待核</span>
        </header>
        ${cases.length ? `
          <section class="ml-support-block" aria-label="对应案例引文">
            <h3>对应案例与精确引文</h3>
            <ol class="ml-case-list">${caseMarkup}</ol>
            ${hiddenCaseMarkup}
          </section>
        ` : '<p class="ml-card-meta">此关系记录没有返回关联案例。</p>'}
      </article>
    `;
  }

  function renderCaseRelation(relation, searchState, index) {
    // Relation descriptors may include other supporting cases. In a case card,
    // its original wording and stance must come only from this case's claims.
    const localIds = new Set(claimIds(relation));
    const localClaims = (relation?.claim_cues || []).filter((claim) => localIds.has(text(claim.claim_id)));
    const localCues = [...new Set(localClaims.map((claim) => text(claim.relation_cue)).filter(Boolean))];
    const localStances = [...new Set(localClaims.map((claim) => text(claim.author_stance)).filter(Boolean))];
    const localRelation = localClaims.length ? {
      ...relation, claim_cues: localClaims, cues: localCues, relation_cues: localCues,
      relation_cue: localCues.length === 1 ? localCues[0] : null,
      author_stance: localStances.length === 1 ? localStances[0] : 'mixed',
    } : relation;
    const relationMarkup = renderRelationLine(localRelation, searchState, { compact: true });
    const quote = text(relation?.quote || relation?.evidence_quote || '');
    return `
      <section class="ml-case-relation">
        ${relationMarkup}
        ${quote ? `<details class="ml-context-fold"><summary>展开本关系对应引文</summary>${quoteMarkup(quote)}</details>` : ''}
      </section>
    `;
  }

  function renderCaseCard(item, index, searchState) {
    const stableKey = text(item?.id || item?.passage_id || `case-${index + 1}`);
    const id = anchorId('ml-case-card', stableKey);
    const title = workTitle(item?.work_key, item?.work_title);
    const location = locationLabel(item);
    const relations = Array.isArray(item?.relations) ? sortedRelations(item.relations, searchState) : [];
    const relationMarkup = relations.map((relation, relationIndex) => renderCaseRelation(relation, searchState, relationIndex)).join('');
    return `
      <article class="ml-card ml-case-card" id="${escape(id)}">
        <header class="ml-card-head">
          <div class="ml-card-main">
            <p class="ml-card-kicker">具体校读点</p>
            <h2>${escape(title)}</h2>
            <p class="ml-card-meta">${escape(location)}</p>
            <div class="ml-card-tools"><a href="#${escape(id)}">定位此案例卡</a></div>
          </div>
          <span class="ml-machine-badge">机器候选 · 待核</span>
        </header>
        ${item?.quote ? `<section class="ml-support-block"><h3>本案例引文</h3>${quoteMarkup(item.quote)}</section>` : ''}
        ${detailFold(stableKey)}
        <section class="ml-support-block ml-case-relations" aria-label="本次命中关系">
          <h3>本次命中关系</h3>
          ${relationMarkup || '<p class="ml-card-meta">此案例没有返回对应关系。</p>'}
        </section>
      </article>
    `;
  }

  function renderMentions(mentions) {
    const total = Math.max(0, Number(mentions?.total) || 0);
    const items = Array.isArray(mentions?.items) ? mentions.items : [];
    elements.mentions.hidden = total === 0 && items.length === 0;
    if (elements.mentions.hidden) return;
    const summary = elements.mentions.querySelector('summary');
    summary.textContent = `正文与证据中的提及（${total} 条补查，不计关系）`;
    if (!items.length) {
      elements.mentionList.innerHTML = '<li class="ml-mention-item">有补查命中，但接口未返回可展示的引文。</li>';
      return;
    }
    elements.mentionList.innerHTML = items.map((item) => {
      const title = workTitle(item?.work_key, item?.work_title || item?.source_title);
      const location = locationLabel(item);
      const label = text(item?.match_scope || item?.mention_type || item?.match_label || '正文或证据');
      const quote = text(item?.quote || item?.excerpt || item?.matched_text || item?.text || item?.preview || '未提供引文');
      return `<li class="ml-mention-item"><span class="ml-mention-meta">${escape(title)} · ${escape(location)} · ${escape(label)}</span><p class="ml-mention-quote">${escape(quote)}</p></li>`;
    }).join('');
  }

  function renderUnsegmented(unsegmented) {
    const total = Math.max(0, Number(unsegmented?.total) || 0);
    const items = Array.isArray(unsegmented?.items) ? unsegmented.items : [];
    elements.unsegmented.hidden = total === 0 && items.length === 0;
    if (elements.unsegmented.hidden) return;
    elements.unsegmented.querySelector('summary').textContent = `未切分原文段（${total} 条补查，不计案例）`;
    if (!items.length) {
      elements.unsegmentedList.innerHTML = '<li class="ml-mention-item">有补查记录，但接口未返回可展示的原文片段。</li>';
      return;
    }
    elements.unsegmentedList.innerHTML = items.map((item) => {
      const id = text(item?.id || item?.source_passage_id || item?.passage_id);
      const title = workTitle(item?.work_key, item?.work_title);
      const location = locationLabel(item);
      const quote = text(item?.quote || item?.claim_quote || item?.matched_text || item?.excerpt || '未提供原文片段');
      const claims = Array.isArray(item?.claims) ? item.claims : [];
      const claimMarkup = claims.map((claim) => {
        const relation = `${relationFormMarkup(claim?.left_form, '左')} ${directionArrow(claim?.directionality)} ${relationFormMarkup(claim?.right_form, '右')}`;
        const cues = relationCues(claim);
        return `<p class="ml-mention-meta">${relation}${cues.length ? ` · 原文措辞：${cues.map(escape).join('、')}` : ''}</p>`;
      }).join('');
      return `<li class="ml-mention-item"><span class="ml-mention-meta">${escape(title)} · ${escape(location)}</span>${claimMarkup}<p class="ml-mention-quote">${escape(quote)}</p>${detailFold(id)}</li>`;
    }).join('');
    attachLazyDetails(elements.unsegmentedList);
  }

  function renderSuppressed(suppressed, searchState) {
    const total = Math.max(0, Number(suppressed?.total) || 0);
    const items = Array.isArray(suppressed?.items) ? suppressed.items : [];
    elements.suppressed.hidden = total === 0 && items.length === 0;
    if (elements.suppressed.hidden) return;
    elements.suppressed.querySelector('summary').textContent = `否定或条件关系（${total} 条，不计主结果）`;
    if (!items.length) {
      elements.suppressedList.innerHTML = '<li class="ml-mention-item">有记录，但接口未返回可展示的关系主张。</li>';
      return;
    }
    elements.suppressedList.innerHTML = items.map((item) => {
      const title = workTitle(item?.work_key, item?.work_title);
      const location = locationLabel(item);
      const leftRaw = item?.source_left_form ?? item?.left_form;
      const rightRaw = item?.source_right_form ?? item?.right_form;
      const left = relationFormMarkup(leftRaw, '左');
      const right = relationFormMarkup(rightRaw, '右');
      const cue = relationCues(item);
      const stance = stanceLabel(item?.author_stance);
      const side = sideLabel(querySide(item, searchState, leftRaw, rightRaw), item?.directionality);
      const relation = `${left} ${directionArrow(item?.directionality)} ${right}`;
      return `<li class="ml-mention-item"><span class="ml-mention-meta">${escape(title)} · ${escape(location)} · ${escape(relationTypeName(item?.relation_type, item?.relation_label))}</span><p class="ml-mention-quote"><strong>${relation}</strong>${side ? ` · ${escape(side)}` : ''}${stance ? ` · ${escape(stance)}` : ''}${cue.length ? ` · 原文措辞：${cue.map(escape).join('、')}` : ''}</p>${item?.quote ? quoteMarkup(item.quote) : ''}${detailFold(item?.claim_id)}</li>`;
    }).join('');
    attachLazyDetails(elements.suppressedList);
  }

  function renderCounts(payload, searchState, itemCount) {
    const matchedClaims = Number(payload?.matched_claim_count ?? payload?.matched_claim_ids?.length ?? 0);
    const viewTotal = Math.max(0, Number(payload?.total ?? itemCount) || 0);
    const page = Math.max(1, Number(payload?.page ?? searchState.page) || 1);
    const pages = Math.max(1, Number(payload?.total_pages) || 1);
    state.currentPage = page;
    state.totalPages = pages;
    elements.pageInput.value = String(page);
    elements.pageInput.max = String(pages);
    elements.pageSummary.textContent = `第 ${page} / ${pages} 页 · 每页 10 张完整卡`;
    elements.previous.disabled = page <= 1;
    elements.next.disabled = page >= pages;
    elements.pager.hidden = pages <= 1 && viewTotal <= pageSize;

    const viewDescription = searchState.view === 'terms'
      ? `${viewTotal} 张字词卡`
      : `${viewTotal} 张案例卡`;
    elements.summary.textContent = `命中 ${matchedClaims} 条关系主张 · ${viewDescription} · 第 ${page}/${pages} 页`;
  }

  function scrollToHash() {
    const rawHash = location.hash.slice(1);
    if (!rawHash) return;
    let hash = rawHash;
    try { hash = decodeURIComponent(rawHash); } catch { /* Keep the browser-provided hash. */ }
    const target = document.getElementById(hash);
    if (target) window.requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }));
  }

  function renderResults(payload, searchState) {
    const items = Array.isArray(payload?.items) ? payload.items : [];
    const orderedItems = searchState.view === 'terms' ? sortedTerms(items, searchState) : items;
    const cards = orderedItems.map((item, index) => searchState.view === 'terms'
      ? renderTermCard(item, index, searchState)
      : renderCaseCard(item, index, searchState)).join('');
    const mentionCount = Number(payload?.mentions?.total) || 0;
    const empty = mentionCount
      ? `<div class="ml-empty">未找到关系卡；正文中有 ${mentionCount} 条提及。<button type="button" class="ml-text-button" data-open-mentions>查看正文</button></div>`
      : '<div class="ml-empty">未找到关系命中。</div>';
    elements.results.innerHTML = cards || empty;
    renderCounts(payload, searchState, items.length);
    renderMentions(payload?.mentions || { total: 0, items: [] });
    renderUnsegmented(payload?.unsegmented || { total: payload?.unsegmented_passage_count || 0, items: [] });
    renderSuppressed(payload?.suppressed || { total: 0, items: [] }, searchState);
    elements.results.querySelector('[data-open-mentions]')?.addEventListener('click', () => {
      elements.mentions.open = true;
      elements.mentions.scrollIntoView({ block: 'start', behavior: 'smooth' });
    });
    attachLazyDetails(elements.results);
    elements.searchStatus.textContent = '检索完成。';
    scrollToHash();
  }

  async function runSearch({ historyMode = 'push', page = 1 } = {}) {
    if (state.timer) window.clearTimeout(state.timer);
    state.timer = 0;
    state.abortController?.abort();
    const requestId = ++state.requestId;
    const searchState = currentState(page);
    state.currentPage = searchState.page;
    if (historyMode !== 'none') writeHistory(searchState, historyMode);
    const controller = new AbortController();
    state.abortController = controller;
    showLoading();
    try {
      const query = searchParamsFor(searchState);
      const payload = await requestJson(`/api/machine/search?${query.toString()}`, { signal: controller.signal });
      if (requestId !== state.requestId) return;
      if (payload?.available === false) {
        elements.searchStatus.textContent = '机器库暂不可用。';
        elements.summary.textContent = '当前机器运行暂不可检索。';
        elements.results.innerHTML = '<div class="ml-error">机器库当前不可用，请稍后重试。</div>';
        elements.mentions.hidden = true;
        elements.unsegmented.hidden = true;
        elements.suppressed.hidden = true;
        elements.pager.hidden = true;
        return;
      }

      if (Number(payload?.page) > 0 && Number(payload.page) !== searchState.page) {
        state.currentPage = Number(payload.page);
        writeHistory(currentState(state.currentPage), 'replace');
      }
      renderResults(payload, searchState);
    } catch (error) {
      if (requestId !== state.requestId || error?.name === 'AbortError') return;
      elements.searchStatus.textContent = '检索失败，可修改条件后重试。';
      elements.summary.textContent = '机器关系暂不可用。';
      elements.results.innerHTML = '<div class="ml-error">机器检索暂不可用，请稍后重试。</div>';
      elements.mentions.hidden = true;
      elements.unsegmented.hidden = true;
      elements.suppressed.hidden = true;
      elements.pager.hidden = true;
    }
  }

  function relationTypeOptions(meta) {
    const raw = meta?.relation_types ?? meta?.relationTypes ?? meta?.types ?? [];
    if (Array.isArray(raw)) {
      return raw.map((item) => typeof item === 'string'
        ? { value: item, label: relationTypeName(item) }
        : { value: text(item?.relation_type || item?.type || item?.value || item?.id), label: relationTypeName(item?.relation_type || item?.type || item?.value || item?.id, item?.relation_label || item?.label || item?.title) })
        .filter((item) => item.value);
    }
    if (raw && typeof raw === 'object') {
      return Object.entries(raw).map(([value, label]) => ({ value, label: relationTypeName(value, typeof label === 'string' ? label : label?.label) }));
    }
    return [];
  }

  function renderRunDetails(meta) {
    const run = meta?.run || {};
    const fields = [
      ['运行 ID', run.id],
      ['解析代码 SHA-256', run.parser_sha256],
      ['输入清单 SHA-256', run.input_manifest_sha256],
    ].filter(([, value]) => value);
    if (meta?.counts && typeof meta.counts === 'object') {
      for (const [key, value] of Object.entries(meta.counts)) {
        if (typeof value === 'number' || typeof value === 'string') fields.push([`数量 · ${key}`, value]);
      }
    }
    elements.runDetails.innerHTML = fields.length
      ? fields.map(([label, value]) => `<dt>${escape(label)}</dt><dd>${escape(value)}</dd>`).join('')
      : '<dt>运行信息</dt><dd>接口未提供运行版本明细。</dd>';
  }

  function updateRunStatus(meta) {
    if (meta?.available === false) {
      elements.runStatus.hidden = false;
      elements.runStatus.textContent = '机器运行当前不可用。';
      return;
    }
    elements.runStatus.textContent = '';
    elements.runStatus.hidden = true;
  }

  async function loadMeta() {
    try {
      const meta = await requestJson('/api/machine/meta');
      state.meta = meta;
      updateRunStatus(meta);
      renderRunDetails(meta);
      const currentValue = elements.relationType.value;
      const options = relationTypeOptions(meta);
      elements.relationType.replaceChildren(new Option('全部类型', ''));
      for (const item of options) elements.relationType.add(new Option(item.label, item.value));
      if (currentValue && !options.some((item) => item.value === currentValue)) {
        elements.relationType.add(new Option(currentValue, currentValue));
      }
      elements.relationType.value = currentValue;
      return true;
    } catch {
      elements.runStatus.hidden = false;
      elements.runStatus.textContent = '运行信息暂不可读取。';
      renderRunDetails(null);
      return false;
    }
  }

  function restoreControlsAndSearch({ fromHistory = false } = {}) {
    cancelPending();
    restoreFromUrl();
    runSearch({ historyMode: 'none', page: state.currentPage, fromHistory });
  }

  elements.form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (state.composing) return;
    cancelPending();
    const page = 1;
    state.currentPage = page;
    runSearch({ historyMode: 'push', page });
  });

  elements.query.addEventListener('input', (event) => {
    if (state.composing || event.isComposing) return;
    scheduleSearch();
  });
  elements.query.addEventListener('compositionstart', () => {
    state.composing = true;
    cancelPending();
    elements.searchStatus.textContent = '输入中……';
    elements.summary.textContent = '输入完成后更新。';
    elements.results.innerHTML = '<div class="ml-empty">输入中……</div>';
    elements.mentions.hidden = true;
    elements.unsegmented.hidden = true;
    elements.suppressed.hidden = true;
    elements.pager.hidden = true;
  });
  elements.query.addEventListener('compositionend', () => {
    state.composing = false;
    scheduleSearch();
  });
  elements.query.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || state.composing || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    cancelPending();
    state.currentPage = 1;
    runSearch({ historyMode: 'push', page: 1 });
  });

  elements.masterWork.addEventListener('change', () => {
    elements.works.forEach((input) => { input.checked = elements.masterWork.checked; });
    syncMasterWork();
    scheduleSearch();
  });
  for (const input of elements.works) {
    input.addEventListener('change', () => {
      syncMasterWork();
      scheduleSearch();
    });
  }
  elements.relationType.addEventListener('change', scheduleSearch);
  elements.position.addEventListener('change', () => {
    elements.positionHelp.hidden = elements.position.value === 'any';
    scheduleSearch();
  });
  elements.match.addEventListener('change', scheduleSearch);

  for (const button of elements.viewButtons) {
    button.addEventListener('click', () => {
      const view = button.dataset.machineView === 'cases' ? 'cases' : 'terms';
      if (view === activeView()) return;
      setView(view);
      state.currentPage = 1;
      runSearch({ historyMode: 'push', page: 1 });
    });
  }

  function goToPage(requested) {
    const parsed = Number(requested);
    if (!Number.isInteger(parsed)) return;
    const page = Math.max(1, Math.min(state.totalPages, parsed));
    elements.pageInput.value = String(page);
    state.currentPage = page;
    runSearch({ historyMode: 'push', page });
  }

  elements.previous.addEventListener('click', () => goToPage(state.currentPage - 1));
  elements.next.addEventListener('click', () => goToPage(state.currentPage + 1));
  elements.jumpPage.addEventListener('click', () => goToPage(elements.pageInput.value));
  elements.pageInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      goToPage(elements.pageInput.value);
    }
  });

  window.addEventListener('popstate', () => restoreControlsAndSearch({ fromHistory: true }));

  (() => {
    restoreFromUrl();
    loadMeta();
    runSearch({ historyMode: 'none', page: state.currentPage });
  })();
})();

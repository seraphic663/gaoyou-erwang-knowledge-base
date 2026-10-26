(() => {
  'use strict';

  const apiBase = '/api/reading-harness';
  const $ = id => document.getElementById(id);
  const el = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  const input = {
    original: $('labOriginal'),
    question: $('labQuestion'),
    sourceWork: $('labSourceWork'),
    sourceLocation: $('labSourceLocation'),
  };
  const evidence = {
    status: $('labEvidenceStatus'),
    list: $('labEvidence'),
    button: $('labRetrieve'),
    previewStatus: $('labPreviewStatus'),
    previewList: $('labPreviewEvidence'),
  };
  const sides = {
    v1: { status: $('labV1Status'), output: $('labV1Output'), button: $('labRunV1'), serial: 0, snapshot: null, citationCards: new Map(), citationLibraryCards: null },
    v2: { status: $('labV2Status'), output: $('labV2Output'), button: $('labRunV2'), serial: 0, snapshot: null, citationCards: new Map(), citationLibraryCards: null },
  };
  const presentation = {
    all: $('labViewAll'),
    steps: $('labViewSteps'),
    navigation: $('labStepNavigation'),
    previous: $('labStepPrevious'),
    next: $('labStepNext'),
    position: $('labStepPosition'),
  };
  const state = {
    records: [],
    actual: null,
    preview: null,
    actualTargets: new Map(),
    retrieveSerial: 0,
    citationReturn: null,
    viewMode: 'all',
    currentStepIndex: 0,
  };
  const stepOrderLabels = ['发疑', '设问', '取证', '释理', '结论'];
  const stepLabels = {
    problem_discovery: '发疑',
    research_question: '设问',
    evidence_collection: '取证',
    reasoning: '释理',
    conclusion: '结论',
  };
  const conclusionLabels = {
    keep_text: '保留原文',
    interpretation: '异读异释',
    emendation_candidate: '校改候选',
    insufficient_evidence: '证据不足',
  };
  const relationLabels = {
    supports: { label: '支持', className: 'supports' },
    contradicts: { label: '反对', className: 'opposes' },
    neutral: { label: '中立', className: 'neutral' },
    parallel: { label: '中立', className: 'neutral' },
    background: { label: '中立', className: 'neutral' },
  };

  function snapshot() {
    return {
      original_text: input.original.value,
      question: input.question.value,
      source_work: input.sourceWork.value,
      source_location: input.sourceLocation.value,
    };
  }
  function same(a, b) {
    return !!a && a.original_text === b.original_text && a.question === b.question
      && a.source_work === b.source_work && a.source_location === b.source_location;
  }
  function status(node, value, kind = '') {
    node.textContent = value;
    node.dataset.state = kind;
  }
  function clearCitationReturn() {
    if (!state.citationReturn) return;
    const target = state.citationReturn;
    target.button.remove();
    state.citationReturn = null;
    target.cleanup?.();
  }
  function focusTarget(node) {
    if (!node) return;
    if (!node.hasAttribute('tabindex')) node.tabIndex = -1;
    node.focus({ preventScroll: true });
  }
  function updatePresentation() {
    const isStepView = state.viewMode === 'steps';
    Object.values(sides).forEach(side => {
      const sections = [...side.output.querySelectorAll('.lab-step')];
      sections.forEach(section => {
        section.hidden = isStepView && Number(section.dataset.stepIndex) !== state.currentStepIndex;
      });
      const library = side.output.querySelector('.lab-citation-library');
      if (side.citationLibraryCards && side.citationCards.size) {
        side.citationCards.forEach(card => side.citationLibraryCards.append(card));
        if (isStepView) {
          const activeStep = sections.find(section => Number(section.dataset.stepIndex) === state.currentStepIndex);
          const stepCards = activeStep?.querySelector('.lab-step-citation-cards');
          if (stepCards) {
            let ids = [];
            try { ids = JSON.parse(activeStep.dataset.citationIds || '[]'); } catch { ids = []; }
            [...new Set(ids)].forEach(id => {
              const card = side.citationCards.get(id);
              if (card) stepCards.append(card);
            });
          }
        }
      }
      if (library) library.hidden = isStepView;
    });
    presentation.all.setAttribute('aria-pressed', String(!isStepView));
    presentation.steps.setAttribute('aria-pressed', String(isStepView));
    presentation.navigation.hidden = !isStepView;
    presentation.position.textContent = `${state.currentStepIndex + 1}/5 · ${stepOrderLabels[state.currentStepIndex]}`;
    presentation.previous.disabled = state.currentStepIndex === 0;
    presentation.next.disabled = state.currentStepIndex === stepOrderLabels.length - 1;
  }
  function revealStepFor(node) {
    if (state.viewMode !== 'steps') return;
    const index = stepIndexFor(node);
    if (!Number.isInteger(index) || index < 0 || index >= stepOrderLabels.length) return;
    state.currentStepIndex = index;
    updatePresentation();
  }
  function stepIndexFor(node) {
    const section = node?.closest?.('.lab-step');
    if (!section) return null;
    const index = Number(section.dataset.stepIndex);
    return Number.isInteger(index) && index >= 0 && index < stepOrderLabels.length ? index : null;
  }
  function revealStepIndex(index) {
    if (state.viewMode !== 'steps' || !Number.isInteger(index) || index < 0 || index >= stepOrderLabels.length) return;
    state.currentStepIndex = index;
    updatePresentation();
  }
  function showReturnButton(destination, label, destinationKind, cleanup = null, context = {}) {
    clearCitationReturn();
    const button = el('button', 'lab-button lab-citation-return', label);
    button.type = 'button';
    button.setAttribute('aria-label', label === '返回步骤' ? '返回刚才点击的步骤引用编号' : '返回刚才定位的引用卡片');
    const target = { destination, button, destinationKind, cleanup, ...context };
    state.citationReturn = target;
    button.addEventListener('click', () => {
      if (state.citationReturn !== target) return;
      if (destination?.isConnected) {
        if (destinationKind === 'step') revealStepFor(destination);
        else if (target.stepLink) revealStepFor(target.stepLink);
        else if (Number.isInteger(target.citationStepIndex)) revealStepIndex(target.citationStepIndex);
        else if (state.viewMode === 'steps' && destination.matches?.('.lab-citation-card')
          && destination.closest('.lab-citation-library')?.hidden) {
          state.viewMode = 'all';
          updatePresentation();
        }
        else revealStepFor(destination);
        destination.scrollIntoView({ behavior: 'smooth', block: 'center' });
        focusTarget(destination);
        if (destination.classList?.contains('lab-citation-card')) {
          destination.classList.add('lab-citation-card--return-target');
          window.setTimeout(() => destination.classList.remove('lab-citation-card--return-target'), 1500);
        }
      }
      const stepLink = destinationKind === 'step' ? null : target.stepLink;
      const citationCard = target.citationCard;
      const citationStepIndex = target.citationStepIndex;
      clearCitationReturn();
      if (stepLink?.isConnected && citationCard?.isConnected) {
        showReturnButton(stepLink, '返回步骤', 'step', null, { stepLink, citationCard, citationStepIndex });
      }
    });
    document.body.append(button);
  }
  function showCitationReturn(card, destinationKind, cleanup = null) {
    const current = state.citationReturn;
    const stepLink = current?.destinationKind === 'step' && current.citationCard === card && current.stepLink?.isConnected
      ? current.stepLink : null;
    const citationStepIndex = stepIndexFor(card)
      ?? (stepLink ? current.citationStepIndex : undefined);
    const context = {
      ...(stepLink ? { stepLink, citationCard: card } : {}),
      ...(citationStepIndex !== undefined && citationStepIndex !== null ? { citationStepIndex } : {}),
    };
    showReturnButton(card, '返回引用', destinationKind, cleanup, context);
  }
  function validate(value) {
    if (!value.original_text.trim() || !value.question.trim()) return '请先填写原文和问题。';
    if ([...value.original_text].length > 6000 || [...value.question].length > 1000) return '原文最多 6000 字，问题最多 1000 字。';
    if ([...value.source_work].length > 200 || [...value.source_location].length > 300) return '书名最多 200 字，篇章或位置最多 300 字。';
    return '';
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 300000);
    const event = {
      time: new Date().toISOString(),
      request: { method: options.method || 'GET', path, body: options.body || null },
    };
    state.records.push(event);
    $('labDownload').disabled = false;
    try {
      const response = await fetch(apiBase + path, {
        method: options.method || 'GET',
        headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });
      const raw = await response.text();
      let payload;
      try { payload = JSON.parse(raw); } catch { throw new Error('服务返回了非 JSON 响应。'); }
      event.http_status = response.status;
      event.response = payload;
      if (!response.ok || payload?.ok === false) {
        const error = new Error(payload?.error?.message || payload?.error || payload?.message || `请求失败（HTTP ${response.status}）`);
        error.payload = payload;
        throw error;
      }
      return payload.data === undefined ? payload : payload.data;
    } catch (error) {
      event.error = { name: error.name, message: error.message };
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
  function errorText(error) {
    return error.name === 'AbortError' ? '请求超时，请稍后重试。' : `请求失败：${error.message}`;
  }
  function fieldText(value) {
    if (value === undefined || value === null || value === '') return '未提供';
    if (Array.isArray(value)) return value.map(fieldText).join('；');
    return typeof value === 'string' ? value : JSON.stringify(value);
  }
  function addSection(container, title, value, className = '') {
    const section = el('section', `lab-output-section ${className}`.trim());
    section.append(el('h4', '', title), el('p', 'lab-input-text', fieldText(value)));
    container.append(section);
    return section;
  }
  function highlightLiteral(node, textValue, quote) {
    if (!quote) return null;
    const start = textValue.indexOf(quote);
    if (start < 0) return null;
    const mark = el('mark', '', quote);
    node.replaceChildren(document.createTextNode(textValue.slice(0, start)), mark, document.createTextNode(textValue.slice(start + quote.length)));
    return mark;
  }
  function highlightCodepoints(node, textValue, start, end) {
    if (!Number.isInteger(start) || !Number.isInteger(end) || end <= start) return null;
    const points = [...textValue];
    if (start < 0 || end > points.length) return null;
    const mark = el('mark', '', points.slice(start, end).join(''));
    node.replaceChildren(
      document.createTextNode(points.slice(0, start).join('')),
      mark,
      document.createTextNode(points.slice(end).join('')),
    );
    return mark;
  }
  function sourceTitle(item) {
    return item?.source_title || item?.title || item?.book_title || item?.source_name || '未注明书名的来源';
  }
  function collectionLabel(value) {
    return ({
      original: '二王原典',
      external_high: '外典·高频',
      external_mid: '外典·中频',
      external_low: '外典·低频',
    })[value] || value || '';
  }
  function headingLabel(value) {
    const parts = Array.isArray(value)
      ? value.map(item => typeof item === 'string' ? item : item?.title || item?.heading || '').filter(Boolean)
      : [value && typeof value === 'object' ? value.title || value.heading || '' : value || ''];
    const label = parts.slice(-2).join(' › ');
    const points = [...label];
    return points.length > 80 ? `${points.slice(0, 80).join('')}…` : label;
  }
  function lineLabel(item) {
    const start = item?.evidence_line_start ?? item?.line_start ?? item?.md_line_start;
    const end = item?.evidence_line_end ?? item?.line_end ?? item?.md_line_end;
    if (!Number.isInteger(Number(start)) || start === undefined || start === null) return '';
    return `原文行 ${start}${end && end !== start ? `–${end}` : ''}`;
  }
  function evidenceItems(data) {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.evidence)) return data.evidence;
    if (Array.isArray(data?.retrieval?.items)) return data.retrieval.items;
    if (Array.isArray(data?.items)) return data.items;
    return [];
  }
  function materialText(item) {
    return item?.evidence_text || item?.matched_text || item?.passage_text || '';
  }
  function contextText(item) {
    return materialText(item);
  }
  function sourceKey(item, index) {
    return String(item?.source_id || item?.work_key || item?.source_title || item?.title || item?.relpath || `source-${index}`);
  }
  function appendHighlightedContext(pre, item, text, quote = '') {
    pre.textContent = text;
    const fullText = typeof item?.full_text === 'string' ? item.full_text : '';
    const target = quote && text.includes(quote) ? quote
      : fullText && text.includes(fullText) ? fullText : '';
    if (target && highlightLiteral(pre, text, target)) return;
    const base = Number.isInteger(item?.context_start_cp)
      ? item.context_start_cp
      : Number.isInteger(item?.reading_start_cp)
        ? item.reading_start_cp
        : Number.isInteger(item?.start_cp) ? item.start_cp : null;
    const start = Number.isInteger(item?.evidence_start_cp) && base !== null
      ? item.evidence_start_cp - base
      : null;
    const end = Number.isInteger(item?.evidence_end_cp) && base !== null
      ? item.evidence_end_cp - base
      : null;
    highlightCodepoints(pre, text, start, end);
  }
  function registerMaterialTarget(map, item, target) {
    for (const key of [item?.evidence_id, item?.chunk_id, item?.result_id, item?.passage_id]) {
      if (key) map.set(String(key), target);
    }
  }
  function renderMaterials(data, container, { targets = null } = {}) {
    container.replaceChildren();
    const items = evidenceItems(data);
    if (!items.length) {
      container.hidden = true;
      return 0;
    }
    container.hidden = false;
    const groups = new Map();
    items.forEach((item, index) => {
      const key = sourceKey(item, index);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({ item, index });
    });

    let groupIndex = 0;
    for (const entries of groups.values()) {
      const source = entries[0].item;
      const group = el('details', 'lab-source-group');
      const summary = el('summary', 'lab-source-summary');
      summary.append(el('span', 'lab-source-title', sourceTitle(source)));
      const count = entries.length;
      summary.append(el('span', 'lab-source-count', `${count} 段材料`));
      group.append(summary);
      const body = el('div', 'lab-source-items');
      entries.forEach(({ item, index }, localIndex) => {
        const card = el('article', 'lab-material-item');
        const heading = headingLabel(item.heading_path || item.heading || item.location);
        card.append(el('h4', 'lab-material-heading', heading || `命中片段 ${localIndex + 1}`));
        const metadata = [collectionLabel(item.collection), lineLabel(item)].filter(Boolean).join(' · ');
        if (metadata) card.append(el('p', 'lab-meta', metadata));
        const excerpt = materialText(item);
        const fullText = typeof item.full_text === 'string' ? item.full_text : '';
        const excerptIsCompleteChunk = Boolean(fullText && excerpt.includes(fullText));
        const excerptNode = excerpt ? el('p', 'lab-evidence-text') : null;
        if (excerptNode) {
          if (excerptIsCompleteChunk) excerptNode.textContent = fullText;
          else {
            const points = [...excerpt];
            excerptNode.textContent = points.length > 240 ? `${points.slice(0, 240).join('')}…` : excerpt;
          }
          card.append(excerptNode);
        }
        const context = contextText(item);
        const nearby = el('details', 'lab-neighbor-details');
        nearby.append(el('summary', '', '查看邻接原文'));
        const pre = el('pre', 'lab-neighbor-text');
        appendHighlightedContext(pre, item, context);
        nearby.append(pre);
        card.append(nearby);
        body.append(card);
        if (targets) registerMaterialTarget(targets, item, { group, card, nearby, pre, excerpt: excerptNode });
      });
      group.append(body);
      if (groupIndex === 0) group.open = true;
      container.append(group);
      groupIndex += 1;
    }
    return items.length;
  }

  function relationFor(citation) {
    return relationLabels[citation?.relation] || relationLabels.neutral;
  }
  function locateOriginal(side, inputAtRun, quote, card) {
    if (same(inputAtRun, snapshot())) {
      showCitationReturn(card, 'original');
      input.original.scrollIntoView({ behavior: 'smooth', block: 'center' });
      input.original.focus();
      const start = quote ? input.original.value.indexOf(quote) : -1;
      if (start >= 0) input.original.setSelectionRange(start, start + quote.length);
      return;
    }
    const locator = el('section', 'lab-output-section lab-original-locator');
    locator.append(el('h4', '', '引用原文'));
    const original = el('pre', 'lab-neighbor-text');
    original.textContent = inputAtRun.original_text;
    const target = highlightLiteral(original, original.textContent, quote);
    locator.append(original);
    side.output.append(locator);
    showCitationReturn(card, 'original', () => locator.remove());
    const focus = target || original;
    focus.scrollIntoView({ behavior: 'smooth', block: 'center' });
    focusTarget(focus);
  }
  function locateMaterial(evidenceId, quote, card) {
    const target = state.actualTargets.get(String(evidenceId || ''));
    if (!target) return;
    target.group.open = true;
    target.nearby.open = true;
    showCitationReturn(card, 'material');
    const currentText = target.pre.textContent;
    const marker = highlightLiteral(target.pre, currentText, quote)
      || (target.excerpt && highlightLiteral(target.excerpt, target.excerpt.textContent, quote));
    const focus = marker || target.card;
    focus.scrollIntoView({ behavior: 'smooth', block: 'center' });
    focusTarget(focus);
  }
  function citationEntries(citations) {
    const reserved = new Set(citations
      .map(citation => citation?.citation_id)
      .filter(value => value !== undefined && value !== null && String(value).trim() !== '')
      .map(String));
    let fallbackNumber = 1;
    return citations.map((citation, index) => {
      const rawId = citation?.citation_id;
      let citationId;
      if (rawId !== undefined && rawId !== null && String(rawId).trim() !== '') {
        citationId = String(rawId);
      } else {
        while (reserved.has(`C${fallbackNumber}`)) fallbackNumber += 1;
        citationId = `C${fallbackNumber}`;
        reserved.add(citationId);
        fallbackNumber += 1;
      }
      return { citation, citationId, index };
    });
  }
  function citationAnchorId(mode, citationId) {
    const encoded = [...String(citationId)].map(character => character.codePointAt(0).toString(16)).join('-') || 'empty';
    return `lab-${mode}-citation-${encoded}`;
  }
  function citationGroups(entries) {
    const groups = new Map();
    entries.forEach(entry => {
      if (!groups.has(entry.citationId)) groups.set(entry.citationId, []);
      groups.get(entry.citationId).push(entry);
    });
    return groups;
  }
  function citationItem(citation, items) {
    const rawId = citation?.evidence_id || citation?.chunk_id || citation?.result_id
      || citation?.passage_id || citation?.id || '';
    if (!rawId || rawId === 'ORIGINAL') return null;
    return items.find(entry => [entry?.evidence_id, entry?.chunk_id, entry?.result_id, entry?.passage_id]
      .some(id => id !== undefined && id !== null && String(id) === String(rawId))) || null;
  }
  function appendCitationContent(container, citation, items) {
    const rawId = citation?.evidence_id || citation?.chunk_id || citation?.result_id
      || citation?.passage_id || citation?.id || '';
    const item = citationItem(citation, items);
    const relation = relationFor(citation);
    const head = el('div', 'lab-citation-head');
    head.append(el('span', `lab-relation-tag lab-relation-tag--${relation.className}`, relation.label));
    head.append(el('span', 'lab-citation-source', rawId === 'ORIGINAL' ? '输入原文' : sourceTitle(item || citation)));
    container.append(head);
    container.append(el('p', 'lab-citation-target', `判断主张：${fieldText(citation?.claim || citation?.target || citation?.judgment)}`));
    const rationale = citation?.rationale || citation?.reason || '';
    container.append(el('p', 'lab-citation-rationale', `理由：${fieldText(rationale)}`));
    container.append(el('blockquote', 'lab-citation-quote', `引文：${fieldText(citation?.quote)}`));
  }
  function showCitationCard(citationId, entries, items, inputAtRun, side, mode) {
    const card = el('article', 'lab-citation-card');
    card.id = citationAnchorId(mode, citationId);
    card.tabIndex = -1;
    card.style.scrollMarginTop = '24px';
    const title = el('h5', 'lab-citation-card-title');
    title.append(el('span', 'lab-citation-id-badge', `[${citationId}]`));
    card.append(title);
    if (entries.length > 1) {
      card.classList.add('lab-citation-card--ambiguous');
      card.append(el('p', 'lab-citation-warning', `响应中有 ${entries.length} 条引用使用同一编号；以下内容已合并展示，编号含义请核对。`));
    }
    entries.forEach((entry, index) => {
      const citation = entry.citation;
      const detail = entries.length > 1 ? el('section', 'lab-citation-variant') : card;
      if (entries.length > 1) detail.append(el('h6', 'lab-citation-variant-title', `同编号记录 ${index + 1}`));
      appendCitationContent(detail, citation, items);
      if (entries.length > 1) card.append(detail);
    });
    if (entries.length !== 1) {
      card.classList.add('lab-citation-card--unavailable');
      card.setAttribute('aria-disabled', 'true');
      return card;
    }
    const citation = entries[0].citation;
    const rawId = citation?.evidence_id || citation?.chunk_id || citation?.result_id
      || citation?.passage_id || citation?.id || '';
    const item = citationItem(citation, items);
    const canLocate = rawId === 'ORIGINAL' || Boolean(item);
    if (canLocate) {
      const sourceLabel = rawId === 'ORIGINAL' ? '输入原文' : '本次材料';
      card.setAttribute('role', 'button');
      card.setAttribute('aria-describedby', 'labCitationHint');
      card.setAttribute('aria-label', `引用 ${citationId}，来源：${sourceLabel}。双击或聚焦后按 Enter、空格键定位。`);
      card.setAttribute('aria-keyshortcuts', 'Enter Space');
      const locate = () => {
        if (rawId === 'ORIGINAL') locateOriginal(side, inputAtRun, citation?.quote || '', card);
        else locateMaterial(rawId, citation?.quote || '', card);
      };
      card.addEventListener('dblclick', locate);
      card.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ' && event.code !== 'Space') return;
        event.preventDefault();
        locate();
      });
    } else {
      card.classList.add('lab-citation-card--unavailable');
      card.setAttribute('aria-disabled', 'true');
    }
    return card;
  }
  function stepCitationIds(step, entries) {
    const ids = Array.isArray(step?.citation_ids)
      ? step.citation_ids.filter(value => value !== undefined && value !== null && String(value) !== '').map(String)
      : [];
    if (ids.length) return [...new Set(ids)];
    return Array.isArray(step?.citation_indexes)
      ? [...new Set(step.citation_indexes
        .filter(index => Number.isInteger(index) && entries[index])
        .map(index => entries[index].citationId))]
      : [];
  }
  function citationReference(id, groups, mode, sourceLink = null) {
    const label = `[${id}]`;
    if (!groups.has(id)) {
      const missing = el('span', 'lab-citation-ref-unavailable', `${label}（缺少对应引用卡）`);
      missing.title = `未找到编号 ${id} 对应的引用卡`;
      return missing;
    }
    const link = el('a', 'lab-citation-link', label);
    link.href = `#${citationAnchorId(mode, id)}`;
    link.addEventListener('click', event => {
      const card = document.getElementById(citationAnchorId(mode, id));
      if (!card) return;
      event.preventDefault();
      const stepLink = sourceLink || link;
      revealStepFor(stepLink);
      const citationStepIndex = stepIndexFor(stepLink);
      showReturnButton(stepLink, '返回步骤', 'step', null, {
        stepLink,
        citationCard: card,
        ...(citationStepIndex !== null ? { citationStepIndex } : {}),
      });
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      focusTarget(card);
      card.classList.add('lab-citation-card--return-target');
      window.setTimeout(() => card.classList.remove('lab-citation-card--return-target'), 1500);
    });
    return link;
  }
  function renderStepText(node, textValue, groups, mode) {
    const pattern = /\[(C\d+(?:\s*[,，、]\s*C\d+)*)\]|(?<![A-Za-z0-9_])(C\d+)(?![A-Za-z0-9_])/g;
    const mentioned = new Set();
    let cursor = 0;
    let match;
    while ((match = pattern.exec(textValue))) {
      node.append(document.createTextNode(textValue.slice(cursor, match.index)));
      const ids = (match[1] || match[2]).split(/[,，、]/).map(id => id.trim()).filter(Boolean);
      ids.forEach((id, index) => {
        mentioned.add(id);
        node.append(citationReference(id, groups, mode));
        if (index < ids.length - 1) node.append(document.createTextNode(' '));
      });
      cursor = pattern.lastIndex;
    }
    node.append(document.createTextNode(textValue.slice(cursor)));
    return mentioned;
  }
  function partialMaterials(payload, inputAtRun) {
    const trace = payload?.trace || {};
    const items = Array.isArray(payload?.evidence) ? payload.evidence
      : Array.isArray(trace.evidence) ? trace.evidence
        : Array.isArray(payload?.retrieval?.items) ? payload.retrieval.items
          : Array.isArray(trace.retrieval?.items) ? trace.retrieval.items : [];
    if (!items.length) return false;
    renderActualMaterials({ evidence: items }, inputAtRun, true);
    return true;
  }
  function renderActualMaterials(data, inputAtRun, partial = false) {
    const items = evidenceItems(data);
    if (state.citationReturn?.destinationKind === 'material') clearCitationReturn();
    state.actualTargets = new Map();
    const count = renderMaterials(items, evidence.list, { targets: state.actualTargets });
    state.actual = { input: inputAtRun, items };
    if (!count) {
      status(evidence.status, partial ? '本次运行没有可展示的检索材料。' : '本次检索没有命中材料。', '');
      return;
    }
    const prefix = partial ? '本次运行检索并送出的材料' : '本次实际送入模型的材料';
    status(evidence.status, `${prefix}共 ${count} 段，按书名或来源归组。`);
  }
  async function retrievePreview() {
    const value = snapshot();
    const invalid = validate(value);
    if (invalid) { status($('labInputStatus'), invalid, 'error'); return; }
    status($('labInputStatus'), '输入已就绪。');
    const serial = ++state.retrieveSerial;
    evidence.button.disabled = true;
    status(evidence.previewStatus, '正在预览检索结果……');
    try {
      const data = await request('/retrieve', { method: 'POST', body: value });
      if (serial !== state.retrieveSerial) return;
      state.preview = { input: value, data };
      const count = renderMaterials(data, evidence.previewList);
      status(evidence.previewStatus, count
        ? `预览到 ${count} 段候选材料；v2 运行时会重新检索。`
        : data?.message || '预览检索没有命中材料。');
      $('labPreview').open = true;
    } catch (error) {
      if (serial === state.retrieveSerial) status(evidence.previewStatus, errorText(error), 'error');
    } finally {
      if (serial === state.retrieveSerial) evidence.button.disabled = false;
    }
  }

  function displayResult(mode, data, inputAtRun) {
    const side = sides[mode];
    const returnTarget = state.citationReturn;
    if (returnTarget && (!returnTarget.destination?.isConnected
      || (returnTarget.stepLink && !returnTarget.stepLink.isConnected)
      || side.output.contains(returnTarget.destination))) clearCitationReturn();
    side.output.replaceChildren();
    side.citationCards = new Map();
    side.citationLibraryCards = null;
    const result = data?.result || data?.response || data || {};
    const citations = Array.isArray(result.citations) ? result.citations : [];
    const entries = citationEntries(citations);
    const groups = citationGroups(entries);
    const steps = Array.isArray(result.steps) ? result.steps : [];
    const items = evidenceItems(data);
    if (mode === 'v2') renderActualMaterials(data, inputAtRun);
    if (steps.length !== 5) {
      side.output.append(el('p', 'lab-note', '服务返回的结果不符合五步校读格式，请下载本次记录查看。'));
      side.snapshot = inputAtRun;
      status(side.status, '结果格式不匹配；完整响应已保留在下载记录中。', 'error');
      return;
    }
    steps.forEach((step, position) => {
      const isConclusion = position === 4 || step.field === 'conclusion';
      const section = el('section', `lab-output-section lab-step${isConclusion ? ' lab-step-conclusion' : ''}`);
      section.dataset.stepIndex = String(position);
      const title = el('h4', 'lab-step-title');
      title.append(el('span', 'lab-step-number', `${position + 1}.`), document.createTextNode(` ${stepLabels[step.field] || step.field || '未命名步骤'}`));
      section.append(title);
      if (isConclusion && conclusionLabels[result.conclusion_type]) {
        section.append(el('span', 'lab-conclusion-type', conclusionLabels[result.conclusion_type]));
      }
      const textValue = fieldText(step.text);
      const textNode = el('p', 'lab-step-text');
      const mentioned = renderStepText(textNode, textValue, groups, mode);
      section.append(textNode);
      if (isConclusion && typeof result.proposed_reading === 'string' && result.proposed_reading.trim()) {
        const reading = el('section', 'lab-proposed-reading');
        const title = result.conclusion_type === 'emendation_candidate' ? '校改候选' : '补充读法';
        reading.append(el('h5', '', title), el('p', '', result.proposed_reading));
        section.append(reading);
      }
      const refs = stepCitationIds(step, entries);
      const referencedIds = [...new Set([...refs, ...mentioned])];
      section.dataset.citationIds = JSON.stringify(referencedIds);
      const notMentioned = refs.filter(id => !mentioned.has(id));
      if (notMentioned.length) {
        const refList = el('div', 'lab-step-citation-links');
        refList.append(el('span', 'lab-step-citation-label', '引用依据：'));
        notMentioned.forEach(id => refList.append(citationReference(id, groups, mode)));
        section.append(refList);
      }
      if (referencedIds.some(id => groups.has(id))) section.append(el('div', 'lab-step-citation-cards'));
      side.output.append(section);
    });
    const library = el('section', 'lab-output-section lab-citation-library');
    library.append(el('h4', '', `${mode} · 【引用依据】（${groups.size} 条）`));
    if (groups.size) {
      const cards = el('div', 'lab-citation-library-cards');
      side.citationLibraryCards = cards;
      groups.forEach((groupEntries, citationId) => {
        const card = showCitationCard(citationId, groupEntries, items, inputAtRun, side, mode);
        side.citationCards.set(citationId, card);
        cards.append(card);
      });
      library.append(cards);
    } else {
      library.append(el('p', 'lab-note', '本次响应没有提供引用卡。'));
    }
    side.output.append(library);
    if (result.uncertainties) addSection(side.output, '未决问题', result.uncertainties);
    updatePresentation();
    side.snapshot = inputAtRun;
    status(side.status, `已完成 · ${data.model_returned || data.model_requested || 'DeepSeek'}${data.elapsed_ms ? ` · ${(data.elapsed_ms / 1000).toFixed(1)} 秒` : ''}`);
  }
  async function generate(mode, value) {
    const side = sides[mode];
    const serial = ++side.serial;
    side.button.disabled = true;
    $('labCompare').disabled = true;
    status(side.status, '正在等待模型回答……');
    try {
      const data = await request('/generate', { method: 'POST', body: { ...value, mode } });
      if (serial !== side.serial) return;
      displayResult(mode, data, value);
    } catch (error) {
      if (serial !== side.serial) return;
      if (mode === 'v2' && !side.output.childElementCount) partialMaterials(error.payload, value);
      status(side.status, errorText(error), 'error');
    } finally {
      if (serial === side.serial) side.button.disabled = false;
      $('labCompare').disabled = sides.v1.button.disabled || sides.v2.button.disabled;
    }
  }
  function run(mode) {
    const value = snapshot();
    const invalid = validate(value);
    if (invalid) { status($('labInputStatus'), invalid, 'error'); return; }
    status($('labInputStatus'), '输入已就绪。');
    if (!sides[mode].button.disabled) generate(mode, value);
  }

  evidence.button.addEventListener('click', retrievePreview);
  presentation.all.addEventListener('click', () => {
    state.viewMode = 'all';
    updatePresentation();
  });
  presentation.steps.addEventListener('click', () => {
    state.viewMode = 'steps';
    updatePresentation();
  });
  presentation.previous.addEventListener('click', () => {
    state.currentStepIndex = Math.max(0, state.currentStepIndex - 1);
    updatePresentation();
  });
  presentation.next.addEventListener('click', () => {
    state.currentStepIndex = Math.min(stepOrderLabels.length - 1, state.currentStepIndex + 1);
    updatePresentation();
  });
  sides.v1.button.addEventListener('click', () => run('v1'));
  sides.v2.button.addEventListener('click', () => run('v2'));
  $('labCompare').addEventListener('click', () => {
    if ($('labCompare').disabled) return;
    const value = snapshot();
    const invalid = validate(value);
    if (invalid) { status($('labInputStatus'), invalid, 'error'); return; }
    status($('labInputStatus'), '两侧按同一份输入发起请求。');
    generate('v1', value);
    generate('v2', value);
  });
  updatePresentation();
  $('labDownload').addEventListener('click', () => {
    const payload = { schema: 'reading-lab.session.v1', exported_at: new Date().toISOString(), records: state.records };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = el('a');
    link.href = url;
    link.download = `reading-lab-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  });
})();

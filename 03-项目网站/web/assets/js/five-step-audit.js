(() => {
  const STEP_DEFINITIONS = [
    { field: 'problem_discovery', label: '发疑' },
    { field: 'research_question', label: '设问' },
    { field: 'evidence_collection', label: '取证' },
    { field: 'reasoning', label: '释理' },
    { field: 'conclusion', label: '结论' },
  ];
  const STATUS_LABELS = {
    pending: '待审',
    accepted: '认可',
    edited: '修改',
    question: '存疑',
    reviewed: '认可',
    needs_revision: '修改',
    uncertain: '存疑',
    active: '当前版本',
    superseded: '已被新版本替代',
    deleted: '已删除（可恢复）',
  };
  const VIEW_MODES = {
    simple: '简洁审校',
    detailed: '细致审校',
  };
  const RAW_STATUS_LABELS = {
    unchecked: '未核验',
    pending: '待处理',
    registered: '已登记',
    missing: '缺失',
    unknown: '未知',
    canonical_active: '原典已登记',
    candidate_available: '有候选来源',
    candidate_registered: '候选已登记',
    candidate_match: '候选命中',
    search_hit_only: '仅搜索命中',
    external_source_pending: '外部来源待处理',
    secondary_citation_match: '二手引文匹配',
    machine_inferred: '机器推断',
    draft: '机器草稿',
  };
  const state = {
    caseId: new URLSearchParams(window.location.search).get('case') || '',
    caseItem: null,
    writeEnabled: false,
    generation: null,
    reviewedSteps: [],
    history: [],
    editingAuditId: null,
    saving: false,
    generating: false,
    viewMode: window.localStorage?.getItem('five-step-view-mode') === 'detailed' ? 'detailed' : 'simple',
    activeStepIndex: 0,
    chooserRequestId: 0,
    writeArmed: false,
  };

  const el = {
    status: document.querySelector('#fiveStepStatus'),
    page: document.querySelector('.five-step-audit-page'),
    start: document.querySelector('#fiveStepStart'),
    recommended: document.querySelector('#fiveStepRecommended'),
    caseSearch: document.querySelector('#fiveStepCaseSearch'),
    caseSearchButton: document.querySelector('#fiveStepCaseSearchButton'),
    chooserStatus: document.querySelector('#fiveStepChooserStatus'),
    chooserResults: document.querySelector('#fiveStepChooserResults'),
    case: document.querySelector('#fiveStepCase'),
    caseTitle: document.querySelector('#fiveStepCaseTitle'),
    caseMeta: document.querySelector('#fiveStepCaseMeta'),
    backLink: document.querySelector('#fiveStepBackLink'),
    sourceContext: document.querySelector('#fiveStepSourceContext'),
    controls: document.querySelector('#fiveStepControls'),
    model: document.querySelector('#fiveStepModel'),
    effort: document.querySelector('#fiveStepEffort'),
    generate: document.querySelector('#fiveStepGenerate'),
    cancelEdit: document.querySelector('#fiveStepCancelEdit'),
    generationMeta: document.querySelector('#fiveStepGenerationMeta'),
    form: document.querySelector('#fiveStepForm'),
    progress: document.querySelector('#fiveStepProgress'),
    viewModeButtons: [...document.querySelectorAll('[data-five-step-view-mode]')],
    stepNav: document.querySelector('#fiveStepStepNav'),
    evidenceOverview: document.querySelector('#fiveStepEvidenceOverview'),
    evidenceOverviewMeta: document.querySelector('#fiveStepEvidenceOverviewMeta'),
    evidenceOverviewList: document.querySelector('#fiveStepEvidenceOverviewList'),
    cards: document.querySelector('#fiveStepCards'),
    reviewer: document.querySelector('#fiveStepReviewer'),
    decision: document.querySelector('#fiveStepDecision'),
    overallNote: document.querySelector('#fiveStepOverallNote'),
    save: document.querySelector('#fiveStepSave'),
    writeArm: document.querySelector('#fiveStepWriteArm'),
    writeStatus: document.querySelector('#fiveStepWriteStatus'),
    saveMessage: document.querySelector('#fiveStepSaveMessage'),
    history: document.querySelector('#fiveStepHistory'),
    historyCount: document.querySelector('#fiveStepHistoryCount'),
    historyList: document.querySelector('#fiveStepHistoryList'),
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]);
  }

  function safeTrim(value) {
    return String(value ?? '').trim();
  }

  function renderInlineMarkdown(value) {
    let html = escapeHtml(value);
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__([^_\n]+)__/g, '<strong>$1</strong>');
    html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    return html;
  }

  // Deliberately small and safe Markdown subset for AI/user prose. Raw HTML,
  // links, tables, and code fences stay escaped instead of becoming markup.
  function renderMarkdownLite(value) {
    const lines = String(value ?? '').replace(/\r\n?/g, '\n').split('\n');
    const blocks = [];
    let paragraph = [];
    let listType = '';
    let listStart = 1;
    let listItems = [];

    const flushParagraph = () => {
      if (!paragraph.length) return;
      blocks.push(`<p>${paragraph.map((line) => renderInlineMarkdown(line)).join('<br />')}</p>`);
      paragraph = [];
    };
    const flushList = () => {
      if (!listItems.length) return;
      const tag = listType === 'ordered' ? 'ol' : 'ul';
      const start = tag === 'ol' && listStart !== 1 ? ` start="${listStart}"` : '';
      blocks.push(`<${tag}${start}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join('')}</${tag}>`);
      listType = '';
      listStart = 1;
      listItems = [];
    };

    lines.forEach((line) => {
      const trimmed = safeTrim(line);
      if (!trimmed) {
        flushParagraph();
        flushList();
        return;
      }
      const ordered = trimmed.match(/^(\d+)[.)]\s+(.+)$/);
      const unordered = trimmed.match(/^[-*•]\s+(.+)$/);
      if (ordered || unordered) {
        flushParagraph();
        const nextType = ordered ? 'ordered' : 'unordered';
        if (listType && listType !== nextType) flushList();
        if (!listType) {
          listType = nextType;
          listStart = ordered ? Number(ordered[1]) : 1;
        }
        listItems.push(safeTrim((ordered || unordered)[2]));
        return;
      }
      flushList();
      paragraph.push(trimmed);
    });
    flushParagraph();
    flushList();
    return blocks.join('');
  }

  function humanStatus(value) {
    const raw = safeTrim(value);
    return RAW_STATUS_LABELS[raw] || raw || '未记录';
  }

  function quoteStatusText(value) {
    return ({
      passed: '引文已与原典核对',
      failed: '引文核对未通过',
      unchecked: '引文还没核对原典',
      pending: '引文等待核对',
      missing: '缺少可核对的引文',
    })[String(value || '')] || '引文状态未确定';
  }

  function resolutionStatusText(value) {
    return ({
      canonical_source_passage: '已经关联原典段落',
      legacy_derived_passage: '来自旧材料整理，尚未回到原典',
      secondary_citation_match: '只在王氏正文中找到二次引文',
      external_source_pending: '外部来源还没确定',
      external_source_resolved: '外部来源已登记，版本仍待核对',
    })[String(value || '')] || '来源还没确定';
  }

  function canonicalStatusText(value) {
    return ({
      canonical_active: '原典段落已登记',
      candidate: '目前只有候选段落',
      unknown: '原典段落还没确认',
    })[String(value || '')] || '原典段落状态未确定';
  }

  function relationTypeText(value) {
    return ({
      synonym: '同义关系',
      phonetic: '声训或音近关系',
      loan: '通假关系',
      variant: '异文或字形关系',
    })[String(value || '')] || '关系未注明';
  }

  function caseStatusText(item) {
    const machine = String(item?.machine_status || '');
    const human = String(item?.human_status || '');
    if (machine === 'draft' && human === 'pending') return '机器已整理，人工尚未审校';
    if (human === 'pending') return '人工尚未审校';
    if (machine === 'draft') return '机器草稿，等待确认';
    return '已有审校记录';
  }

  function snippet(value, limit = 180) {
    const text = safeTrim(String(value ?? '').replace(/\s+/g, ' '));
    return text.length > limit ? `${text.slice(0, limit)}…` : text;
  }

  function effortLabel(value) {
    return ({ none: '不启用思考', low: '低', high: '高', max: '最高' })[value] || value || '未记录';
  }

  function selectedDraft(field) {
    return state.generation?.draft?.find((step) => step.field === field) || null;
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, { cache: 'no-store', ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || `HTTP ${response.status}`);
    }
    return payload;
  }

  function plainText(passage) {
    return passage?.raw_text || passage?.plain_text || passage?.normalized_text || '';
  }

  function renderRetrievalContext(retrieval) {
    if (!retrieval || retrieval.ok === false) {
      return `
        <article class="five-step-context-block five-step-retrieval-block">
          <div class="five-step-evidence-ref-head">
            <h3>四部著作检索</h3>
            <span class="five-step-evidence-tag">未完成</span>
          </div>
          <p class="five-step-context-meta">本次原文检索没有完成，草稿不能把检索结果当作依据。</p>
          <p class="five-step-context-text">${escapeHtml(retrieval?.message || '暂时无法连接原文库。')}</p>
        </article>
      `;
    }
    const items = Array.isArray(retrieval.items) ? retrieval.items : [];
    const trace = retrieval.trace || {};
    const crossWork = trace.fallback_from_work_key;
    const heading = crossWork ? '跨作品候选参考' : '四部著作检索';
    const badge = items.length ? `${items.length} 条候选` : '没有命中';
    const summary = items.length
      ? (crossWork
        ? `当前作品没有直接命中，下面是从其他作品补充找到的候选材料，只作参考。`
        : '这些原文段落会随当前案例一起提供给五步草稿。')
      : '本次没有找到可展示的原文段落，草稿不会把不存在的命中写成依据。';
    return `
      <article class="five-step-context-block five-step-retrieval-block">
        <div class="five-step-evidence-ref-head">
          <h3>${escapeHtml(heading)}</h3>
          <span class="five-step-evidence-tag">${escapeHtml(badge)}</span>
        </div>
        <p class="five-step-context-meta">检索词：${escapeHtml(retrieval.query || '未记录')} · ${escapeHtml(summary)}</p>
        ${items.length ? `<div class="five-step-retrieval-list">${items.map((material, index) => {
          const title = material.document_title || material.work_key || '作品未注明';
          const location = [material.section_title, material.entry_title].filter(Boolean).join(' · ') || '篇目未注明';
          const text = material.passage_text || '没有可展示的原文。';
          const referenceLabel = crossWork ? '候选参考' : '原文候选';
          return `
            <article class="five-step-retrieval-item">
              <div class="five-step-evidence-ref-head">
                <strong>${escapeHtml(referenceLabel)} ${index + 1} · ${escapeHtml(title)}</strong>
                <span class="five-step-evidence-tag">${escapeHtml(canonicalStatusText(material.canonical_status || 'unknown'))}</span>
              </div>
              <p class="five-step-context-meta">${escapeHtml(location)} · ${escapeHtml(material.match_reason || '正文片段命中')}</p>
              <p class="five-step-context-text">${escapeHtml(text)}</p>
            </article>
          `;
        }).join('')}</div>` : ''}
      </article>
    `;
  }

  function renderSourceContext(item) {
    const passage = item.source_passage;
    const provenance = item.provenance || {};
    const passageText = plainText(passage);
    const evidenceCount = item.evidences?.length || 0;
    const unresolved = (item.evidences || []).filter((evidence) => ['unchecked', 'pending', 'missing', 'unknown'].includes(String(evidence.quote_check || ''))).length;
    const sourceState = passage?.canonical_status || 'unknown';
    const sourceLabel = passage?.document_title || passage?.section_title || item.source_work || provenance.source_file || '来源未注明';
    const evidenceSummary = evidenceCount
      ? `${evidenceCount} 条引文材料${unresolved ? `，其中 ${unresolved} 条还没核对原典` : '，引文均已完成状态登记'}`
      : '当前案例没有关联引文材料';
    const related = item.related_materials || { related_cases: [], related_terms: [] };
    const relatedCases = related.related_cases || [];
    const relatedTerms = related.related_terms || [];
    el.sourceContext.innerHTML = `
      <article class="five-step-context-block">
        <div class="five-step-evidence-ref-head">
          <h3>来源段落</h3>
          <span class="five-step-evidence-tag">${escapeHtml(canonicalStatusText(sourceState))}</span>
        </div>
        <p class="five-step-context-meta">来源：${escapeHtml(sourceLabel)}</p>
        <p class="five-step-context-text">${escapeHtml(snippet(passageText || 'V2 中未关联可展示的来源段落。', 260))}</p>
        ${passageText.length > 260 ? `<details class="five-step-inline-fold"><summary>展开完整来源段落</summary><p class="five-step-full-copy">${escapeHtml(passageText)}</p></details>` : ''}
        <div class="five-step-engineering-detail">
          passage_id: <code>${escapeHtml(passage?.passage_id || item.source_passage_id || 'null')}</code> · canonical_status: <code>${escapeHtml(sourceState)}</code><br />
          source_file: <code>${escapeHtml(provenance.source_file || passage?.source_file || 'null')}</code>
        </div>
      </article>
      <article class="five-step-context-block">
        <div class="five-step-evidence-ref-head">
          <h3>材料概况</h3>
          <span class="five-step-evidence-tag">${escapeHtml(evidenceCount)} 条材料</span>
        </div>
        <p class="five-step-context-meta">${escapeHtml(evidenceSummary)}</p>
        <p>${escapeHtml(caseStatusText(item))}</p>
        <p>目标典籍：${escapeHtml(item.target_work || '尚未明确')}</p>
        <div class="five-step-engineering-detail">
          machine_status: <code>${escapeHtml(item.machine_status || 'null')}</code> · human_status: <code>${escapeHtml(item.human_status || 'null')}</code><br />
          target_work: <code>${escapeHtml(item.target_work || 'null')}</code> · target_passage_id: <code>${escapeHtml(item.target_passage_id || 'null')}</code>
        </div>
      </article>
      ${renderRetrievalContext(item.retrieval_materials)}
      ${relatedCases.length || relatedTerms.length ? `
        <article class="five-step-context-block five-step-related-block">
          <div class="five-step-evidence-ref-head">
            <h3>相关材料</h3>
            <span class="five-step-evidence-tag">用于比较</span>
          </div>
          <p class="five-step-context-meta">系统根据来源、目标典籍和词语关系找到了相近材料；它们只用于比较，不替代当前案例的引文。</p>
          ${relatedCases.length ? `<div class="five-step-related-list">${relatedCases.map((relatedCase) => `
            <a class="five-step-related-case" href="./annotation-workbench.html?case=${encodeURIComponent(relatedCase.case_id)}">
              <span><strong>${escapeHtml(relatedCase.case_title || '未命名案例')}</strong><small>${escapeHtml(relatedCase.source_work || '来源未注明')} · ${escapeHtml(relatedCase.target_work || '目标典籍未明确')}</small></span>
              <small>${escapeHtml(relatedCase.relation || '材料相近')} · 打开</small>
            </a>
          `).join('')}</div>` : ''}
          ${relatedTerms.length ? `<div class="five-step-related-terms">${relatedTerms.map((term) => `<span class="five-step-related-term">${escapeHtml(term.source_term || '未注明')} → ${escapeHtml(term.target_term || '未注明')} · ${escapeHtml(relationTypeText(term.relation_type))}</span>`).join('')}</div>` : ''}
        </article>
      ` : ''}
    `;
  }

  function renderCase(item) {
    state.caseItem = item;
    el.caseTitle.textContent = item.case_title || '未命名案例';
    el.caseMeta.textContent = `${item.source_work || '来源未注明'} · ${item.target_work || '目标典籍未明确'} · ${caseStatusText(item)}`;
    el.backLink.href = `./v2-database.html#browse`;
    renderSourceContext(item);
    el.case.hidden = false;
    el.controls.hidden = false;
    el.status.textContent = '已载入 V2 案例。确认所选案例和来源状态后，可生成五步草稿。';
  }

  function renderCaseChooserItems(root, items, emptyText = '当前没有匹配的案例。') {
    if (!root) return;
    if (!items.length) {
      root.innerHTML = `<p class="compact-note">${escapeHtml(emptyText)}</p>`;
      return;
    }
    root.innerHTML = items.map((item) => `
      <button type="button" class="five-step-case-option" data-five-step-case-id="${escapeHtml(item.case_id)}">
        <span class="five-step-case-option-main">
          <strong>${escapeHtml(item.case_title || '未命名案例')}</strong>
          <small>${escapeHtml(item.source_work || '来源未注明')} · ${escapeHtml(item.target_work || '目标典籍未明确')}</small>
        </span>
        <span class="five-step-case-option-meta">
          <small>${escapeHtml(caseStatusText(item))}</small>
          <span>开始审校 →</span>
        </span>
      </button>
    `).join('');
    root.querySelectorAll('[data-five-step-case-id]').forEach((button) => {
      button.addEventListener('click', () => {
        const caseId = button.dataset.fiveStepCaseId;
        if (caseId) window.location.href = `./annotation-workbench.html?case=${encodeURIComponent(caseId)}`;
      });
    });
  }

  async function loadCaseChooser({ query = '', recommended = false } = {}) {
    const requestId = ++state.chooserRequestId;
    const target = recommended ? el.recommended : el.chooserResults;
    if (!target) return;
    const searchQuery = safeTrim(query);
    target.innerHTML = '<p class="compact-note">正在读取可审校案例……</p>';
    if (el.chooserStatus && !recommended) el.chooserStatus.textContent = '';
    try {
      const params = new URLSearchParams({ page: '1', pageSize: '6' });
      if (searchQuery) params.set('q', searchQuery);
      const payload = await requestJson(`/api/v2/cases?${params.toString()}`);
      if (requestId !== state.chooserRequestId) return;
      const items = Array.isArray(payload.items) ? payload.items : [];
      renderCaseChooserItems(target, items);
      if (el.chooserStatus && !recommended) {
        el.chooserStatus.textContent = searchQuery
          ? `找到 ${payload.total || items.length} 条案例，当前显示前 ${items.length} 条。`
          : `当前工作库共有 ${payload.total || items.length} 条案例，当前显示前 ${items.length} 条。`;
      }
    } catch (error) {
      if (requestId !== state.chooserRequestId) return;
      target.innerHTML = `<p class="compact-note">案例读取失败：${escapeHtml(error.message)}</p>`;
      if (el.chooserStatus && !recommended) el.chooserStatus.textContent = '请检查本地 V2 测试库是否已生成。';
    }
  }

  function evidenceStatus(evidence) {
    const data = evidence.data || {};
    return {
      summary: [
        quoteStatusText(evidence.quote_check),
        resolutionStatusText(data.source_resolution),
        evidence.source_passage ? canonicalStatusText(evidence.source_passage.canonical_status) : '没有关联的原典段落',
      ].join('；'),
      raw: `quote_check=${evidence.quote_check || 'null'} · source_resolution=${data.source_resolution || 'null'} · canonical_status=${evidence.source_passage?.canonical_status || 'null'}`,
    };
  }

  function renderEvidenceCard(evidence, compact = false) {
    const index = Number(evidence.evidence_index);
    const status = evidenceStatus(evidence);
    const referenced = state.generation?.draft?.some((step) => (step.evidence_refs || []).map(Number).includes(index));
    const data = evidence.data || {};
    const note = data.evidence_note || data.note || data.relation_note || '';
    return `<article class="${compact ? 'five-step-evidence-ref' : 'five-step-evidence-overview-item'}"${compact ? '' : ` id="fiveStepEvidence-${escapeHtml(index)}"`}>
      <div class="five-step-evidence-ref-head">
        <strong>材料 ${escapeHtml(index)} · ${escapeHtml(evidence.source_work || evidence.external_cited_work || '来源未注明')}</strong>
        ${referenced ? '<span class="five-step-evidence-tag">AI 已引用</span>' : ''}
      </div>
      <p class="five-step-context-meta">${escapeHtml(status.summary)}</p>
      <blockquote>${escapeHtml(snippet(evidence.quote || '（无引文）', compact ? 140 : 220))}</blockquote>
      ${note ? `<p class="five-step-material-note">${escapeHtml(note)}</p>` : ''}
      <div class="five-step-engineering-detail">
        ${escapeHtml(status.raw)}<br />
        external_status: <code>${escapeHtml(evidence.external_status || 'null')}</code> · edition_status: <code>${escapeHtml(evidence.external_edition_status || 'null')}</code> · passage_status: <code>${escapeHtml(evidence.external_passage_status || 'null')}</code><br />
        source_resolution_note: <code>${escapeHtml(data.evidence_note || data.note || data.relation_note || 'null')}</code>
      </div>
    </article>`;
  }

  function renderEvidenceRefs(step) {
    const refs = Array.isArray(step.evidence_refs) ? step.evidence_refs : [];
    if (!refs.length) {
      return `<p class="compact-note">AI 未指定可直接支撑本步的证据；请人工判断是否缺证。<button type="button" class="five-step-inline-link" data-five-step-open-evidence="overview">查看证据总览</button></p>`;
    }
    const evidenceByIndex = new Map((state.caseItem?.evidences || []).map((item) => [Number(item.evidence_index), item]));
    return `<div class="five-step-evidence-refs">${refs.map((index) => {
      const evidence = evidenceByIndex.get(Number(index));
      if (!evidence) return `<article class="five-step-evidence-ref">证据 ${escapeHtml(index)}：当前案例中找不到该编号，请核查。</article>`;
      return renderEvidenceCard(evidence, true);
    }).join('')}</div>`;
  }

  function renderEvidenceOverview() {
    if (!el.evidenceOverviewList || !state.caseItem) return;
    const evidences = Array.isArray(state.caseItem.evidences) ? state.caseItem.evidences : [];
    const referenced = new Set((state.generation?.draft || []).flatMap((step) => step.evidence_refs || []).map(Number));
    const unresolved = evidences.filter((evidence) => ['unchecked', 'pending', 'missing', 'unknown'].includes(String(evidence.quote_check || ''))).length;
    el.evidenceOverviewMeta.textContent = `${evidences.length} 条材料 · AI 已引用 ${referenced.size} 条 · ${unresolved} 条还没核对原典`;
    el.evidenceOverviewList.innerHTML = evidences.length
      ? evidences.map((evidence) => renderEvidenceCard(evidence)).join('')
      : '<p class="compact-note">本案例没有可展开的 evidence。</p>';
  }

  function renderStepNav() {
    if (!el.stepNav) return;
    el.stepNav.innerHTML = STEP_DEFINITIONS.map(({ field, label }, index) => {
      const reviewed = state.reviewedSteps[index] || { status: 'pending' };
      const current = index === state.activeStepIndex;
      const complete = reviewed.status !== 'pending';
      return `<button type="button" class="five-step-step-nav-button${current ? ' is-current' : ''}${complete ? ' is-complete' : ''}" data-five-step-nav="${index}" aria-current="${current ? 'step' : 'false'}" aria-label="${escapeHtml(`${label}${complete ? '，已完成' : ''}`)}">
        <span class="five-step-step-nav-number">0${index + 1}</span>
        <span class="five-step-step-nav-label">${escapeHtml(label)}</span>
      </button>`;
    }).join('');
  }

  function renderSteps() {
    if (!state.generation || !state.reviewedSteps.length) return;
    const draftByField = new Map(state.generation.draft.map((step) => [step.field, step]));
    renderStepNav();
    el.cards.innerHTML = STEP_DEFINITIONS.map(({ field, label }, index) => {
      const draft = draftByField.get(field) || { text: '', evidence_refs: [], review_questions: [] };
      const reviewed = state.reviewedSteps[index] || { status: 'pending', text: draft.text, comment: '' };
      const questions = draft.review_questions?.length
        ? `<ul>${draft.review_questions.map((question) => `<li>${escapeHtml(question)}</li>`).join('')}</ul>`
        : '<p class="compact-note">这一步暂时没有单独的待核问题。</p>';
      const showHumanFields = ['edited', 'question'].includes(reviewed.status);
      const decisionLabels = { accepted: '认可', edited: '修改', question: '存疑' };
      const decisionTitles = {
        accepted: '这一步可以直接采用',
        edited: '你知道应该怎样改写',
        question: '材料或解释还没有确认',
      };
      const actionButtons = ['accepted', 'edited', 'question'].map((decision) => `<button type="button" title="${escapeHtml(decisionTitles[decision])}" class="five-step-decision-button${reviewed.status === decision ? ' is-selected' : ''}" data-five-step-decision="${decision}" data-five-step-field="${escapeHtml(field)}">${decisionLabels[decision]}</button>`).join('');
      const humanTextLabel = reviewed.status === 'edited' ? '修改后的文本' : '人工暂定文本';
      const humanCommentLabel = reviewed.status === 'edited' ? '修改理由' : '存疑理由和待核问题';
      const humanTextPlaceholder = reviewed.status === 'edited' ? '写下你确认后的替代表述' : '写下目前可以保留的暂定表述';
      const humanFields = showHumanFields
        ? `<label>${humanTextLabel}
            <textarea data-five-step-text="${escapeHtml(field)}" rows="6" placeholder="${escapeHtml(humanTextPlaceholder)}">${escapeHtml(reviewed.text)}</textarea>
          </label>
          <label>${humanCommentLabel}
            <textarea data-five-step-comment="${escapeHtml(field)}" rows="3" placeholder="${escapeHtml(humanCommentLabel)}">${escapeHtml(reviewed.comment)}</textarea>
          </label>`
        : '';
      return `
        <details class="five-step-step" data-step-field="${escapeHtml(field)}"${index === state.activeStepIndex ? ' open' : ''}>
          <summary>
            <span class="five-step-step-number">0${index + 1}</span>
            <span class="five-step-step-summary-label"><span class="five-step-step-summary-title" role="heading" aria-level="3">${escapeHtml(label)}</span></span>
          </summary>
          <div class="five-step-step-body">
            <div class="five-step-step-grid">
              <div>
                <p class="section-kicker">AI 生成内容</p>
                <div class="five-step-ai-draft">${renderMarkdownLite(draft.text || 'AI 没有生成这一步的文字。')}</div>
                <details class="five-step-review-questions">
                  <summary>需要再核对 · ${draft.review_questions?.length || 0} 条</summary>
                  ${questions}
                </details>
                <div class="five-step-review-fields">
                  <p class="section-kicker">审校决定</p>
                  <div class="five-step-review-actions">${actionButtons}</div>
                  ${humanFields}
                </div>
              </div>
              <aside class="five-step-evidence-panel">
                <div class="five-step-evidence-panel-heading">
                  <div>
                  <p class="section-kicker">本步材料</p>
                    <h4>本步相关材料</h4>
                  </div>
                  <span class="five-step-evidence-tag">${(draft.evidence_refs || []).length} 条</span>
                </div>
                ${renderEvidenceRefs(draft)}
              </div>
            </div>
          </div>
        </details>
      `;
    }).join('');
    renderEvidenceOverview();
    updateSaveButton();
  }

  function generationSummary(generation) {
    const usage = generation.usage || {};
    const usageText = Number.isFinite(Number(usage.total_tokens)) ? ` · ${usage.total_tokens} tokens` : '';
    const budgetText = Number.isFinite(Number(generation.max_tokens)) ? ` · budget ${generation.max_tokens}` : '';
    const compact = `已生成五步草稿 · ${new Date(generation.generated_at).toLocaleString()}`;
    if (state.viewMode === 'simple') return compact;
    return `${compact} · 模型 ${generation.model_requested} · 思考强度 ${effortLabel(generation.reasoning_effort)} · API 返回 ${generation.model_returned}${budgetText}${usageText} · prompt ${generation.prompt_version}`;
  }

  function renderProgress() {
    if (!el.progress) return;
    const reviewed = state.reviewedSteps.filter((step) => step.status !== 'pending').length;
    el.progress.textContent = state.reviewedSteps.length
      ? `${reviewed}/${STEP_DEFINITIONS.length}`
      : '0/5';
  }

  function applyViewMode(mode = state.viewMode) {
    state.viewMode = VIEW_MODES[mode] ? mode : 'simple';
    if (el.page) el.page.dataset.viewMode = state.viewMode;
    el.viewModeButtons.forEach((button) => {
      const active = button.dataset.fiveStepViewMode === state.viewMode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    try {
      window.localStorage?.setItem('five-step-view-mode', state.viewMode);
    } catch {
      // Storage is optional; the page still works when it is unavailable.
    }
    if (state.generation && el.generationMeta && !el.generationMeta.classList.contains('pending') && !el.generationMeta.classList.contains('error')) {
      el.generationMeta.textContent = generationSummary(state.generation);
    }
    renderProgress();
  }

  function updateSaveButton() {
    const reviewer = safeTrim(el.reviewer?.value);
    const decisionsComplete = state.reviewedSteps.length === STEP_DEFINITIONS.length
      && state.reviewedSteps.every((step) => step.status !== 'pending' && safeTrim(step.text)
        && (!['edited', 'question'].includes(step.status) || safeTrim(step.comment)));
    const writeReady = state.writeEnabled && state.writeArmed;
    el.save.disabled = !writeReady || !state.generation || !reviewer || !decisionsComplete || state.saving;
    renderProgress();
    if (!state.writeEnabled) {
      el.writeStatus.textContent = '当前是只读预览，服务器还没有开放保存。';
      el.writeStatus.classList.remove('five-step-write-disabled');
      if (el.writeArm) {
        el.writeArm.disabled = true;
        el.writeArm.checked = false;
      }
    } else if (!state.writeArmed) {
      el.writeStatus.textContent = '完成审校后，打开“允许保存本次审校”才能保存。';
      el.writeStatus.classList.remove('five-step-write-disabled');
    } else {
      el.writeStatus.textContent = '本次审校已允许保存。';
      el.writeStatus.classList.remove('five-step-write-disabled');
    }
  }

  function renderHistory(records) {
    state.history = Array.isArray(records) ? records : [];
    el.historyCount.textContent = `${state.history.length} 条`;
    el.history.hidden = false;
    if (!state.history.length) {
      el.historyList.innerHTML = '<p class="compact-note">这个案例还没有提交过五步审计记录。</p>';
      return;
    }
    el.historyList.innerHTML = state.history.map((record) => {
      const audit = record.audit || {};
      const finalSteps = Array.isArray(audit.reviewed_steps) ? audit.reviewed_steps : [];
      const label = STATUS_LABELS[audit.overall_decision] || audit.overall_decision || '未注明';
      const stateLabel = STATUS_LABELS[record.record_state] || record.record_state || '未注明';
      const stateClass = record.record_state === 'deleted'
        ? 'deleted'
        : record.record_state === 'superseded' ? 'superseded' : 'active';
      const managementActions = record.record_state === 'deleted'
        ? `<button type="button" class="page-link page-link-muted toolbar-button" data-audit-action="restore" data-audit-id="${escapeHtml(record.audit_id)}">恢复</button>`
        : `${record.record_state === 'active'
          ? `<button type="button" class="page-link page-link-muted toolbar-button" data-audit-action="edit" data-audit-id="${escapeHtml(record.audit_id)}">修改</button>`
          : ''}
           <button type="button" class="search-clear toolbar-button" data-audit-action="delete" data-audit-id="${escapeHtml(record.audit_id)}">删除</button>`;
      return `
        <details class="five-step-history-record">
          <summary>${escapeHtml(record.submitted_at)} · ${escapeHtml(record.reviewer)} · ${escapeHtml(label)} <span class="five-step-record-state ${stateClass}">${escapeHtml(stateLabel)}</span></summary>
          <div class="five-step-history-actions">${managementActions}</div>
          <p class="five-step-context-meta five-step-engineering-detail">版本 ${escapeHtml(record.record_version || 1)}${record.supersedes_audit_id ? ` · 修改自 ${escapeHtml(record.supersedes_audit_id)}` : ''}${record.superseded_by_audit_id ? ` · 新版本 ${escapeHtml(record.superseded_by_audit_id)}` : ''}</p>
          <p class="five-step-context-meta five-step-engineering-detail">API 返回 ${escapeHtml(record.model_returned)} · operation ${escapeHtml(record.operation_id)} · 来源指纹 ${escapeHtml(record.case_fingerprint)}</p>
          ${audit.overall_note ? `<p>${escapeHtml(audit.overall_note)}</p>` : ''}
          ${record.record_state === 'deleted' ? `<p class="five-step-context-meta">删除人：${escapeHtml(record.deleted_by || '未记录')} · ${escapeHtml(record.deleted_at || '')}${record.delete_reason ? ` · 原因：${escapeHtml(record.delete_reason)}` : ''}</p>` : ''}
          ${finalSteps.map((step, index) => `
            <div class="five-step-history-step">
              <strong>${escapeHtml(STEP_DEFINITIONS[index]?.label || step.field)} · ${escapeHtml(STATUS_LABELS[step.status] || step.status)}</strong>
              <div class="five-step-history-markdown">${renderMarkdownLite(step.text)}</div>
              ${step.comment ? `<div class="five-step-context-meta">审校意见：${renderMarkdownLite(step.comment)}</div>` : ''}
            </div>
          `).join('')}
        </details>
      `;
    }).join('');
  }

  function generationFromRecord(record) {
    const audit = record.audit || {};
    return {
      case_id: record.case_id,
      case_fingerprint: record.case_fingerprint,
      prompt_version: record.prompt_version,
      model_requested: record.model_requested,
      model_returned: record.model_returned,
      reasoning_effort: record.reasoning_effort,
      max_tokens: audit.output_budget_tokens || null,
      generated_at: record.generated_at,
      usage: audit.usage || null,
      retrieval_materials: audit.retrieval_materials || null,
      draft: Array.isArray(audit.ai_draft) ? audit.ai_draft : [],
      source_audit_id: record.audit_id,
    };
  }

  function beginEditRecord(record) {
    if (!record || record.record_state !== 'active') return;
    const audit = record.audit || {};
    if (!Array.isArray(audit.ai_draft) || !Array.isArray(audit.reviewed_steps)) {
      el.saveMessage.textContent = '该记录缺少完整五步内容，无法在页面上修改。';
      el.saveMessage.className = 'five-step-save-message error';
      return;
    }
    state.editingAuditId = record.audit_id;
    state.generation = generationFromRecord(record);
    state.reviewedSteps = audit.reviewed_steps.map((step) => ({
      field: step.field,
      status: step.status,
      text: step.text,
      comment: step.comment || '',
    }));
    el.model.value = record.model_requested;
    el.effort.value = record.reasoning_effort;
    el.model.disabled = true;
    el.effort.disabled = true;
    el.generate.disabled = true;
    el.cancelEdit.hidden = false;
    el.generate.textContent = '修改模式中';
    el.reviewer.value = record.reviewer || '';
    el.decision.value = audit.overall_decision || 'reviewed';
    el.overallNote.value = audit.overall_note || '';
    el.generationMeta.className = 'five-step-generation-meta';
    el.generationMeta.textContent = `正在修改版本 ${record.record_version || 1} · ${generationSummary(state.generation)} · 保存后将生成新版本，原记录保留。`;
    el.generationMeta.hidden = false;
    el.form.hidden = false;
    el.save.textContent = '保存修改（生成新版本）';
    el.saveMessage.className = 'five-step-save-message';
    el.saveMessage.textContent = '';
    renderSteps();
    el.form.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function exitEditMode() {
    state.editingAuditId = null;
    el.model.disabled = false;
    el.effort.disabled = false;
    el.generate.disabled = false;
    el.generate.textContent = '重新生成五步草稿';
    el.cancelEdit.hidden = true;
    el.save.textContent = '保存本次审校';
  }

  function cancelEditMode() {
    exitEditMode();
          state.generation = null;
          state.reviewedSteps = [];
          state.writeArmed = false;
          if (el.writeArm) el.writeArm.checked = false;
          el.cards.innerHTML = '';
    el.form.hidden = true;
    el.generationMeta.hidden = true;
    el.saveMessage.textContent = '';
    updateSaveButton();
  }

  function managementActor() {
    const current = safeTrim(el.reviewer?.value);
    if (current) return current;
    return safeTrim(window.prompt('请输入本次操作人姓名或 reviewer ID：'));
  }

  function newOperationId(prefix) {
    return globalThis.crypto?.randomUUID
      ? `${prefix}-${globalThis.crypto.randomUUID()}`
      : `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  }

  async function manageHistoryRecord(action, auditId) {
    const record = state.history.find((item) => item.audit_id === auditId);
    if (!record) return;
    if (action === 'edit') {
      beginEditRecord(record);
      return;
    }
    const actor = managementActor();
    if (!actor) {
      el.saveMessage.className = 'five-step-save-message error';
      el.saveMessage.textContent = '未提供操作人，操作未执行。';
      return;
    }
    if (action === 'delete') {
      if (!window.confirm('删除这条审计记录？记录会被软删除并保留在历史中，可随后恢复。')) return;
      try {
        await requestJson('/api/v2/five-step-audits', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            audit_id: auditId,
            deleted_by: actor,
            delete_reason: '网站记录管理操作',
            operation_id: newOperationId('delete-audit'),
          }),
        });
        if (state.editingAuditId === auditId) exitEditMode();
        el.saveMessage.className = 'five-step-save-message';
        el.saveMessage.textContent = '记录已软删除；原始内容仍可在历史中恢复。';
        await loadHistory();
      } catch (error) {
        el.saveMessage.className = 'five-step-save-message error';
        el.saveMessage.textContent = `删除失败：${error.message}`;
      }
      return;
    }
    if (action === 'restore') {
      try {
        await requestJson('/api/v2/five-step-audits', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mode: 'restore',
            audit_id: auditId,
            restored_by: actor,
            operation_id: newOperationId('restore-audit'),
          }),
        });
        el.saveMessage.className = 'five-step-save-message';
        el.saveMessage.textContent = '记录已恢复。';
        await loadHistory();
      } catch (error) {
        el.saveMessage.className = 'five-step-save-message error';
        el.saveMessage.textContent = `恢复失败：${error.message}`;
      }
    }
  }

  async function loadHistory() {
    const payload = await requestJson(`/api/v2/five-step-audits?case_id=${encodeURIComponent(state.caseId)}`);
    state.writeEnabled = Boolean(payload.write_enabled);
    renderHistory(payload.records);
    updateSaveButton();
  }

  async function generateDraft() {
    if (!state.caseItem || state.generating) return;
    const hasEdits = state.reviewedSteps.some((step) => step.comment || step.status !== 'pending');
    if (hasEdits && !window.confirm('重新生成会替换当前 AI 草稿，并清空本次尚未保存的逐步审校意见。继续吗？')) return;

    state.generating = true;
    el.generate.disabled = true;
    el.generate.setAttribute('aria-busy', 'true');
    el.generate.textContent = '正在生成……';
    el.status.textContent = '正在读取所选 V2 案例并请求 DeepSeek……';
    el.saveMessage.textContent = '';
    el.generationMeta.className = 'five-step-generation-meta pending';
    const waitSeconds = el.effort.value === 'max' ? 180 : 120;
    el.generationMeta.textContent = `正在请求 ${el.model.options[el.model.selectedIndex]?.text || el.model.value} · 思考 ${effortLabel(el.effort.value)}；服务器最多等待 ${waitSeconds} 秒。`;
    el.generationMeta.hidden = false;
    try {
      const response = await requestJson('/api/v2/five-step-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: state.caseId,
          model: el.model.value,
          reasoning_effort: el.effort.value,
        }),
      });
      state.generation = response;
      if (response.retrieval_materials) {
        state.caseItem.retrieval_materials = response.retrieval_materials;
        renderSourceContext(state.caseItem);
      }
      state.editingAuditId = null;
      state.activeStepIndex = 0;
      state.reviewedSteps = response.draft.map((step) => ({
        field: step.field,
        status: 'pending',
        text: step.text,
        comment: '',
      }));
      el.generationMeta.textContent = generationSummary(response);
      el.generationMeta.className = 'five-step-generation-meta';
      el.generationMeta.hidden = false;
      el.form.hidden = false;
      renderSteps();
      el.status.textContent = '五步草稿已生成。请逐步检查措辞、证据编号和来源核验状态。';
    } catch (error) {
      el.status.textContent = `生成失败：${error.message}`;
      el.generationMeta.className = 'five-step-generation-meta error';
      el.generationMeta.textContent = `生成失败：${error.message}`;
      el.generationMeta.hidden = false;
    } finally {
      state.generating = false;
      el.generate.disabled = false;
      el.generate.removeAttribute('aria-busy');
      el.generate.textContent = '重新生成五步草稿';
    }
  }

  function onStepInput(event) {
    const element = event.target;
    const field = element.dataset.fiveStepText || element.dataset.fiveStepComment || element.dataset.fiveStepStatus;
    if (!field) return;
    const step = state.reviewedSteps.find((item) => item.field === field);
    if (!step) return;
    if (element.dataset.fiveStepText) step.text = element.value;
    else if (element.dataset.fiveStepComment) step.comment = element.value;
    else step.status = element.value;
    updateSaveButton();
  }

  function setStepDecision(field, decision) {
    const index = STEP_DEFINITIONS.findIndex((item) => item.field === field);
    const step = state.reviewedSteps[index];
    if (!step) return;
    state.activeStepIndex = index;
    step.status = decision;
    if (decision === 'accepted') {
      step.text = selectedDraft(field)?.text || step.text;
    } else if (step.text === selectedDraft(field)?.text) {
      step.text = '';
    }
    renderSteps();
  }

  function onStepDecision(event) {
    const button = event.target.closest('[data-five-step-decision]');
    if (!button) return;
    event.preventDefault();
    setStepDecision(button.dataset.fiveStepField, button.dataset.fiveStepDecision);
  }

  function onStepNavigation(event) {
    const button = event.target.closest('[data-five-step-nav]');
    if (!button) return;
    event.preventDefault();
    const index = Number(button.dataset.fiveStepNav);
    const detail = el.cards.querySelectorAll('[data-step-field]')[index];
    if (!detail) return;
    state.activeStepIndex = index;
    detail.open = true;
    renderStepNav();
    detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function openEvidenceOverview(event) {
    const button = event.target.closest('[data-five-step-open-evidence]');
    if (!button || !el.evidenceOverview) return;
    event.preventDefault();
    el.evidenceOverview.open = true;
    el.evidenceOverview.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function submitAudit(event) {
    event.preventDefault();
    if (el.save.disabled || !state.generation) return;
    state.saving = true;
    updateSaveButton();
    el.saveMessage.className = 'five-step-save-message';
    el.saveMessage.textContent = '正在保存本次审校……';
    const operationId = globalThis.crypto?.randomUUID
      ? globalThis.crypto.randomUUID()
      : `five-step-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
    const editingAuditId = state.editingAuditId;
    const body = editingAuditId
      ? {
        audit_id: editingAuditId,
        case_id: state.caseId,
        reviewer: safeTrim(el.reviewer?.value),
        operation_id: operationId,
        reviewed_steps: state.reviewedSteps,
        overall_decision: el.decision.value,
        overall_note: el.overallNote.value,
      }
      : {
        case_id: state.caseId,
        reviewer: safeTrim(el.reviewer?.value),
        operation_id: operationId,
        case_fingerprint: state.generation.case_fingerprint,
        model_requested: state.generation.model_requested,
        model_returned: state.generation.model_returned,
        reasoning_effort: state.generation.reasoning_effort,
        prompt_version: state.generation.prompt_version,
        generated_at: state.generation.generated_at,
        output_budget_tokens: state.generation.max_tokens,
        review_view_mode: state.viewMode,
        usage: state.generation.usage,
        retrieval_materials: state.generation.retrieval_materials || state.caseItem?.retrieval_materials || null,
        ai_draft: state.generation.draft,
        reviewed_steps: state.reviewedSteps,
        overall_decision: el.decision.value,
        overall_note: el.overallNote.value,
      };
    try {
      const payload = await requestJson('/api/v2/five-step-audits', {
        method: editingAuditId ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      el.saveMessage.textContent = editingAuditId
        ? '修改已保存为新版本，原版本仍保留。'
        : '本次审校已保存。';
      exitEditMode();
      state.generation = null;
      state.reviewedSteps = [];
      el.cards.innerHTML = '';
      el.form.hidden = true;
      el.generationMeta.hidden = true;
      await loadHistory();
    } catch (error) {
      el.saveMessage.textContent = `保存失败：${error.message}`;
      el.saveMessage.classList.add('error');
    } finally {
      state.saving = false;
      updateSaveButton();
    }
  }

  async function init() {
    if (!state.caseId) {
      el.status.textContent = '请选择一个 V2 案例开始审校。';
      el.start.hidden = false;
      await loadCaseChooser({ recommended: true });
      return;
    }
    try {
      const item = await requestJson(`/api/v2/case?id=${encodeURIComponent(state.caseId)}`);
      try {
        item.retrieval_materials = await requestJson(`/api/v2/retrieve?case_id=${encodeURIComponent(state.caseId)}`);
      } catch (retrievalError) {
        item.retrieval_materials = { ok: false, message: retrievalError.message };
      }
      renderCase(item);
      await loadHistory();
    } catch (error) {
      el.status.textContent = `无法打开该 V2 案例：${error.message}`;
      el.start.hidden = false;
      await loadCaseChooser({ recommended: true });
    }
  }

  el.generate?.addEventListener('click', generateDraft);
  el.caseSearchButton?.addEventListener('click', () => {
    loadCaseChooser({ query: el.caseSearch?.value || '' });
  });
  el.caseSearch?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      loadCaseChooser({ query: el.caseSearch.value || '' });
    }
  });
  el.cancelEdit?.addEventListener('click', cancelEditMode);
  el.cards?.addEventListener('input', onStepInput);
  el.cards?.addEventListener('change', onStepInput);
  el.cards?.addEventListener('click', onStepDecision);
  el.cards?.addEventListener('click', openEvidenceOverview);
  el.stepNav?.addEventListener('click', onStepNavigation);
  el.viewModeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      applyViewMode(button.dataset.fiveStepViewMode);
      renderEvidenceOverview();
      renderSteps();
    });
  });
  el.historyList?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-audit-action]');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    manageHistoryRecord(button.dataset.auditAction, button.dataset.auditId);
  });
  el.reviewer?.addEventListener('input', updateSaveButton);
  el.writeArm?.addEventListener('change', () => {
    state.writeArmed = Boolean(el.writeArm.checked && state.writeEnabled);
    updateSaveButton();
  });
  el.form?.addEventListener('submit', submitAudit);

  applyViewMode(state.viewMode);
  init();
})();

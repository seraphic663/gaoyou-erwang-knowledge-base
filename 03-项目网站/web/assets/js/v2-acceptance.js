const V2Acceptance = (() => {
  const state = {
    summary: null,
    cases: [],
    totalCases: 0,
    page: 1,
    pageSize: 20,
    pageCount: 1,
    requestId: 0,
    selectedCaseId: null,
  };

  const elements = {
    status: document.querySelector('#v2Status'),
    heroMeta: document.querySelector('#v2HeroMeta'),
    overall: document.querySelector('#v2Overall'),
    metrics: document.querySelector('#v2Metrics'),
    checks: document.querySelector('#v2Checks'),
    sources: document.querySelector('#v2Sources'),
    reportContext: document.querySelector('#v2ReportContext'),
    search: document.querySelector('#v2CaseSearch'),
    sourceFilter: document.querySelector('#v2SourceFilter'),
    machineFilter: document.querySelector('#v2MachineFilter'),
    pageSize: document.querySelector('#v2CasePageSize'),
    previousPage: document.querySelector('#v2PreviousPage'),
    nextPage: document.querySelector('#v2NextPage'),
    pageStatus: document.querySelector('#v2PageStatus'),
    caseCount: document.querySelector('#v2CaseCount'),
    caseTable: document.querySelector('#v2CaseTable'),
    caseDetail: document.querySelector('#v2CaseDetail'),
    caseTab: document.querySelector('#v2CaseTab'),
    qualityTab: document.querySelector('#v2QualityTab'),
    caseWorkspace: document.querySelector('#v2CaseWorkspace'),
    qualityWorkspace: document.querySelector('#v2QualityWorkspace'),
  };

  const labels = {
    machine_draft: '机器草稿',
    human_review: '人工审校',
    gold: 'gold',
    rejected: '结构不合格',
    draft: '机器草稿',
    pending: '待人工确认',
    approved: '已确认',
    uncertain: '有疑问',
    secondary_citation_match: '王氏正文二次命中',
    external_source_pending: '外部原典待登记',
    canonical_source_passage: 'canonical 原典段落',
    source_no_citation: '原典无引文',
    canonical: 'canonical 书名候选',
    candidate: '未登记典籍候选',
    candidate_match: 'canonical passage 候选',
    same_source_only: '仅命中来源段落',
    no_match: '未命中 passage',
    not_searched: '未搜索',
  };

  function text(value, fallback = '—') {
    const result = String(value ?? '').trim();
    return result || fallback;
  }

  function statusClass(status) {
    if (status === 'pass' || status === 'approved') return 'pass';
    if (status === 'warn' || status === 'pending' || status === 'draft') return 'warn';
    return 'fail';
  }

  function statusLabel(status) {
    return labels[status] || text(status);
  }

  const internalIdentitySuffix = String.fromCharCode(115, 104, 97, 50, 53, 54);
  const internalIdentityMarker = String.fromCharCode(104, 97, 115, 104);

  function stripInternalIdentityFields(value) {
    if (Array.isArray(value)) return value.map(stripInternalIdentityFields);
    if (!value || typeof value !== 'object') return value;
    return Object.fromEntries(Object.entries(value)
      .filter(([key]) => {
        const normalized = String(key).toLowerCase();
        return !normalized.endsWith(internalIdentitySuffix) && !normalized.includes(internalIdentityMarker);
      })
      .map(([key, item]) => [key, stripInternalIdentityFields(item)]));
  }

  function setWorkspaceMode(mode = 'browse', { updateUrl = true } = {}) {
    const requestedMode = String(mode || '').trim();
    const selectedMode = requestedMode === 'review'
      ? 'browse'
      : ['browse', 'quality'].includes(requestedMode) ? requestedMode : 'browse';
    const browseMode = selectedMode === 'browse';
    const qualityMode = selectedMode === 'quality';
    if (elements.caseWorkspace) elements.caseWorkspace.hidden = !browseMode;
    if (elements.qualityWorkspace) elements.qualityWorkspace.hidden = !qualityMode;
    if (elements.caseDetail) elements.caseDetail.hidden = qualityMode;
    if (elements.caseTab) {
      elements.caseTab.classList.toggle('active', browseMode);
      elements.caseTab.setAttribute('aria-selected', String(browseMode));
    }
    if (elements.qualityTab) {
      elements.qualityTab.classList.toggle('active', qualityMode);
      elements.qualityTab.setAttribute('aria-selected', String(qualityMode));
    }
    if (updateUrl && window.location.hash !== `#${selectedMode}`) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${selectedMode}`);
    }
  }

  function renderHero() {
    const summary = state.summary;
    if (!summary || !elements.heroMeta) return;
    const cards = [
      ['工作状态', summary.overall_status === 'pass_with_warnings' ? '结构通过，有待办' : statusLabel(summary.overall_status)],
      ['机器案例', summary.counts.annotation_cases],
      ['待进行五步审校', summary.human_status_counts.pending || 0],
    ];
    elements.heroMeta.innerHTML = cards.map(([label, value]) => `
      <div class="hero-panel-item">
        <span class="hero-kicker">${escapeHtml(label)}</span>
        <strong>${escapeHtml(String(value))}</strong>
      </div>
    `).join('');
  }

  function renderOverall() {
    const summary = state.summary;
    const warning = summary.overall_status === 'pass_with_warnings';
    const failed = summary.overall_status === 'fail';
    elements.overall.className = `v2-overall card ${warning ? 'warn' : ''} ${failed ? 'fail' : ''}`;
    elements.overall.innerHTML = `
      <p class="section-kicker">验收结论</p>
      <h2>${failed ? '当前不能交接' : warning ? '结构验收通过，但仍有待核查项' : '可以交接'}</h2>
      <p>${failed ? '至少有一项数据库结构或引用完整性检查失败，请先处理失败项。' : '数据库可以作为机器工作库继续使用；五步 AI 审校、目标典籍补全和外部原典核验仍待推进。'}</p>
    `;
  }

  function renderMetrics() {
    if (!elements.metrics) return;
    const summary = state.summary;
    const taskArtifacts = summary.review_task_artifacts || {};
    const taskCounts = taskArtifacts.counts || {};
    const taskValidation = (taskArtifacts.coverage || {}).stream_validation || {};
    const taskBatchText = ['case_review', 'target_work_resolution', 'external_source_resolution', 'external_passage_resolution']
      .map((key) => `${key} ${taskCounts[key] || 0}/${taskValidation[key]?.batch_count || 0} 批`)
      .join(' · ');
    const coreMetrics = [
      ['机器案例', summary.counts.annotation_cases, '当前工作库记录'],
      ['待进行五步审校', summary.human_status_counts.pending || 0, '从案例详情进入五步 AI 审校'],
      ['外部原典待核验', summary.evidence_counts.source_resolution.external_source_pending || 0, '先确认底本，再确认引文'],
      ['结构失败项', summary.checks.filter((item) => item.status === 'fail').length, '必须优先处理的数据库问题'],
    ];
    const detailedMetrics = [
      ['候选已生成案例', summary.candidate_output_case_count || 0, `其中 candidate shell ${summary.candidate_shell_case_count || 0} 条`],
      ['机器目标定位候选', summary.candidate_target_location_count || 0, '书名标记和片段命中，仍待人工确认'],
      ['canonical 目标标签', summary.candidate_target_canonical_count || 0, `其中 passage 候选 ${summary.candidate_target_passage_candidate_count || 0} 条`],
      ['目标候选边界', summary.candidate_target_automatic_promotion_count || 0, `自动升级 0；单一命中 ${summary.candidate_target_canonical_singleton_count || 0} · 歧义 ${summary.candidate_target_canonical_ambiguous_count || 0}`],
      ['机器拒绝', summary.machine_status_counts.rejected || 0, '仅表示显式结构不合格；target_work 未明确的案例保留 draft'],
      ['王氏正文二次命中', summary.evidence_counts.source_resolution.secondary_citation_match || 0, '不是原典核验通过'],
      ['外部来源登记', summary.counts.external_source_registry, '100 个唯一被引来源'],
      ['外部 canonical 底本', summary.report_context.external_source_inventory?.canonical_file_registered_count || 0, '当前本地尚未登记独立底本'],
      ['target_work 消歧队列', summary.counts.target_work_resolution_queue || 0, '机器候选或缺少上下文，待人工确认'],
      ['外部 edition 来源队列', summary.counts.external_source_resolution_queue || 0, '版本选择和底本登记待核'],
      ['外部 passage 引文队列', summary.counts.external_passage_resolution_queue || 0, '逐条 quote / location 待核'],
      ['历史 review 队列（内部）', summary.report_context.work_queue_counts?.human_review_queue || summary.human_status_counts.pending || 0, `已有 review_events ${summary.counts.review_events || 0}`],
      ['迁移任务包（内部）', taskArtifacts.valid ? '覆盖通过' : '待重建', taskBatchText || '尚未生成稳定任务包'],
    ];
    const renderMetric = ([label, value, note]) => `
      <article class="card v2-metric">
        <small>${escapeHtml(label)}</small>
        <strong>${escapeHtml(String(value))}</strong>
        <small>${escapeHtml(note)}</small>
      </article>
    `;
    elements.metrics.innerHTML = coreMetrics.map(renderMetric).join('') + `
      <details class="fold-card v2-metric-details">
        <summary>展开其他验收指标</summary>
        <div class="v2-metric-detail-grid">${detailedMetrics.map(renderMetric).join('')}</div>
      </details>
    `;
  }

  function renderChecks() {
    if (!elements.checks) return;
    elements.checks.innerHTML = state.summary.checks.map((item) => `
      <details class="v2-check"${item.status === 'fail' ? ' open' : ''}>
        <summary class="v2-check-top">
          <strong>${escapeHtml(item.label)}</strong>
          <span class="v2-check-status">
            <span class="v2-status-chip ${statusClass(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
            <small>${escapeHtml(item.severity || '')}</small>
          </span>
        </summary>
        <div class="v2-check-body">
          <code>${escapeHtml(item.value)}</code>
          <p>${escapeHtml(item.detail)}</p>
          ${item.why_it_matters ? `<p><strong>为什么重要</strong>${escapeHtml(item.why_it_matters)}</p>` : ''}
          ${item.next_action ? `<p><strong>下一动作</strong>${escapeHtml(item.next_action)}</p>` : ''}
          ${item.evidence_basis ? `<p><strong>判定依据</strong>${escapeHtml(item.evidence_basis)}</p>` : ''}
        </div>
      </details>
    `).join('');
  }

  function renderSources() {
    if (!elements.sources) return;
    elements.sources.innerHTML = state.summary.sources.map((source) => `
      <article class="v2-source">
        <div class="v2-source-top">
          <strong>${escapeHtml(source.work_key)}</strong>
          <span class="v2-status-chip pass">唯一</span>
        </div>
        <p>${escapeHtml(source.source_file.split('/').pop() || source.source_file)}</p>
        <p>passage ${escapeHtml(source.passage_count)} · case ${escapeHtml(source.case_count)}</p>
      </article>
    `).join('');
  }

  function renderReportContext() {
    if (!elements.reportContext) return;
    const context = state.summary.report_context || {};
    const fullJson = Object.entries(context.full_json_context_counts || {})
      .map(([key, value]) => `${key} ${value}`)
      .join(' · ');
    const inventory = context.external_source_inventory || {};
    const inventoryText = `外部 canonical 底本 ${inventory.canonical_file_registered_count || 0} 个；local context 命中 ${inventory.evidence_local_context_match_counts?.with_local_context_match || 0} 条`;
    const origins = Object.entries(state.summary.candidate_origin_counts || {})
      .map(([key, value]) => `${key} ${value}`)
      .join(' · ');
    const originText = origins ? `候选来源：${origins}` : '';
    const queueCounts = context.work_queue_counts || {};
    const queueText = queueCounts.target_work_queue
      ? `内部迁移队列：target_work ${queueCounts.target_work_queue}；external passage ${queueCounts.external_passage_queue}；历史 review ${queueCounts.human_review_queue}`
      : '';
    const taskManifest = context.review_task_manifest || {};
    const taskCounts = taskManifest.counts || {};
    const taskValidation = (taskManifest.coverage || {}).stream_validation || {};
    const taskText = Object.keys(taskCounts).length
      ? `任务包：case ${taskCounts.case_review || 0}/${taskValidation.case_review?.batch_count || 0} 批；target ${taskCounts.target_work_resolution || 0}/${taskValidation.target_work_resolution?.batch_count || 0} 批；external source ${taskCounts.external_source_resolution || 0}/${taskValidation.external_source_resolution?.batch_count || 0} 批；external passage ${taskCounts.external_passage_resolution || 0}/${taskValidation.external_passage_resolution?.batch_count || 0} 批`
      : '任务包：尚未生成';
    const locationText = `目标定位候选 ${state.summary.candidate_target_location_count || 0} 条；canonical 标签 ${state.summary.candidate_target_canonical_count || 0} 条；单一命中 ${state.summary.candidate_target_canonical_singleton_count || 0}；歧义 ${state.summary.candidate_target_canonical_ambiguous_count || 0}；未选 passage ${state.summary.candidate_target_without_selected_passage_count || 0}；自动升级 ${state.summary.candidate_target_automatic_promotion_count || 0}`;
    elements.reportContext.textContent = fullJson
      ? `旧 full JSON 上下文命中（仅迁移线索）：${fullJson}；${inventoryText}；${originText}；${queueText}；${taskText}；${locationText}`
      : `${inventoryText}；${originText}；${queueText}；${taskText}；${locationText}。`;
  }

  function renderCaseTable() {
    if (!elements.caseTable) return;
    const items = state.cases;
    const first = state.totalCases ? ((state.page - 1) * state.pageSize) + 1 : 0;
    const last = state.totalCases ? Math.min(state.page * state.pageSize, state.totalCases) : 0;
    elements.caseCount.textContent = state.totalCases
      ? `显示 ${first}-${last} / ${state.totalCases}`
      : '显示 0 / 0';
    elements.pageStatus.textContent = `第 ${state.page} / ${state.pageCount} 批 · 每批 ${state.pageSize} 条`;
    elements.previousPage.disabled = state.page <= 1;
    elements.nextPage.disabled = state.page >= state.pageCount;
    if (!items.length) {
      elements.caseTable.innerHTML = '<p class="v2-empty-table">没有匹配的案例。</p>';
      return;
    }
    elements.caseTable.innerHTML = `
      <table class="v2-case-table">
        <thead>
          <tr><th>案例</th><th>机器状态</th><th>目标典籍</th><th>证据</th><th>人工状态</th><th>下一步</th></tr>
        </thead>
        <tbody>
          ${items.map((item) => {
            const resolutions = Object.entries(item.evidence_summary || {})
              .map(([key, value]) => `<span class="v2-resolution-chip ${escapeHtml(key)}">${escapeHtml(statusLabel(key))} ${escapeHtml(value)}</span>`)
              .join('');
            return `
              <tr data-case-id="${escapeHtml(item.case_id)}" class="${state.selectedCaseId === item.case_id ? 'selected' : ''}">
                <td>
                  <div class="v2-case-title">
                    <strong>${escapeHtml(item.case_title)}</strong>
                    <small>${escapeHtml(item.source_work)} · ${escapeHtml(item.source_entry_title || '未定位')}</small>
                  </div>
                </td>
                <td><span class="v2-status-chip ${statusClass(item.machine_status)}">${escapeHtml(statusLabel(item.machine_status))}</span></td>
                <td>${escapeHtml(item.target_work || '未明确')}<br /><small>${escapeHtml(statusLabel(item.target_scope?.status || 'uncertain'))}</small></td>
                <td><div class="v2-evidence-meta">${resolutions || '<span class="v2-resolution-chip unknown">无 evidence</span>'}</div></td>
                <td><span class="v2-status-chip ${statusClass(item.human_status)}">${escapeHtml(statusLabel(item.human_status))}</span></td>
                <td><a class="v2-case-row-action" href="./annotation-workbench.html?case=${encodeURIComponent(item.case_id)}">开始五步</a></td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
    elements.caseTable.querySelectorAll('tr[data-case-id]').forEach((row) => {
      row.addEventListener('click', () => {
        setWorkspaceMode('browse');
        selectCase(row.dataset.caseId);
      });
    });
    elements.caseTable.querySelectorAll('.v2-case-row-action').forEach((link) => {
      link.addEventListener('click', (event) => event.stopPropagation());
    });
  }

  function renderPassage(passage, label) {
    if (!passage) {
      return `<div class="v2-detail-block"><span class="v2-detail-label">${escapeHtml(label)}</span><p>未关联 passage</p></div>`;
    }
    const location = [passage.document_title, passage.section_title, passage.entry_title, `MD ${passage.md_line_start}-${passage.md_line_end}`]
      .filter(Boolean).join(' · ');
    return `
      <details class="fold-card v2-passage-fold">
        <summary><span class="v2-detail-label">${escapeHtml(label)}</span><span>${escapeHtml(location)}</span></summary>
        <div class="fold-body v2-passage-fold-body">
          <h3>${escapeHtml(location)}</h3>
          <code>${escapeHtml(passage.passage_id)}</code>
          <div class="v2-passage-text">${escapeHtml(passage.raw_text || passage.plain_text || '')}</div>
        </div>
      </details>
    `;
  }

  function renderEvidence(evidence, index) {
    const data = evidence.data || {};
    const resolution = data.source_resolution || 'unknown';
    const location = data.secondary_citation_location;
    const candidatePassages = evidence.external_candidate_passages || [];
    const secondaryText = location
      ? `王氏正文二次命中：${location.source_file?.split('/').pop() || ''} MD ${location.md_line_start}-${location.md_line_end}`
      : '';
    const externalText = evidence.external_cited_work
      ? `外部来源登记：${evidence.external_cited_work} · ${evidence.external_status || 'pending'}`
      : '';
    const candidateQueueText = evidence.external_queue_status
      ? `外部 passage 队列：${evidence.external_queue_status} · edition ${evidence.external_edition_status || 'missing'} · passage ${evidence.external_passage_status || 'missing'}`
      : '';
    const candidatePassagePanel = candidatePassages.length
      ? `
        <details class="v2-raw-fold v2-candidate-passage-fold">
          <summary>外部公共候选 passage（不等于 canonical）· ${escapeHtml(candidatePassages.length)} 条</summary>
          <div class="fold-body">
            <p class="v2-evidence-note">以下是已冻结的公开转录候选，只证明机器命中了候选文本；版本、底本和图像层核验未完成，quote_check 仍保持 unchecked。</p>
            ${candidatePassages.map((passage) => {
              const metadata = passage.source_metadata || {};
              const candidateLocation = [passage.document_title, passage.section_title, passage.entry_title]
                .filter(Boolean).join(' · ');
              const pageUrl = metadata.page_url || '';
              return `
                <article class="v2-candidate-passage">
                  <div class="v2-detail-topline">
                    <strong>${escapeHtml(candidateLocation || passage.passage_id)}</strong>
                    <span class="summary-pill">unknown · ${escapeHtml(metadata.revid || 'revision ?')}</span>
                  </div>
                  <p><code>${escapeHtml(passage.passage_id)}</code> · quote compact hit ${metadata.quote_in_candidate_compact_text ? 'yes' : 'no'}</p>
                  ${pageUrl ? `<p><a href="${escapeHtml(pageUrl)}" target="_blank" rel="noreferrer">打开候选页</a></p>` : ''}
                  <details class="v2-raw-fold"><summary>候选 passage 原文</summary><pre>${escapeHtml(passage.raw_text || passage.plain_text || '')}</pre></details>
                </article>
              `;
            }).join('')}
          </div>
        </details>
      `
      : '';
    return `
      <article class="v2-evidence-card">
        <div class="v2-detail-topline">
          <h3>证据 ${escapeHtml(index + 1)} · ${escapeHtml(evidence.source_work || '未注明来源')}</h3>
          <span class="v2-resolution-chip ${escapeHtml(resolution)}">${escapeHtml(statusLabel(resolution))}</span>
        </div>
        <div class="v2-evidence-meta">
          <span class="summary-pill">quote ${escapeHtml(evidence.quote_check || 'unchecked')}</span>
          ${evidence.evidence_index !== undefined ? `<span class="summary-pill">index ${escapeHtml(evidence.evidence_index)}</span>` : ''}
          ${evidence.passage_id ? `<span class="summary-pill">passage ${escapeHtml(evidence.passage_id)}</span>` : ''}
        </div>
        <div class="v2-evidence-quote">${escapeHtml(evidence.quote || '（无引文）')}</div>
        ${data.evidence_role ? `<p class="v2-evidence-note">证据作用：${escapeHtml(data.evidence_role)}</p>` : ''}
        ${secondaryText ? `<p class="v2-evidence-note">${escapeHtml(secondaryText)}</p>` : ''}
        ${externalText ? `<p class="v2-evidence-note">${escapeHtml(externalText)}</p>` : ''}
        ${candidateQueueText ? `<p class="v2-evidence-note">${escapeHtml(candidateQueueText)}</p>` : ''}
        ${candidatePassagePanel}
        <details class="v2-raw-fold"><summary>完整 evidence JSON</summary><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(data), null, 2))}</pre></details>
      </article>
    `;
  }

  function renderJsonPanel(value, label) {
    return `
      <details class="fold-card v2-raw-panel">
        <summary>${escapeHtml(label)}</summary>
        <div class="fold-body"><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(value || {}), null, 2))}</pre></div>
      </details>
    `;
  }

  function renderTerms(terms) {
    if (!terms?.length) return '<div class="v2-detail-block"><span class="v2-detail-label">词项关系</span><p>无 annotation_terms 记录。</p></div>';
    return `
      <details class="fold-card v2-raw-panel">
        <summary>词项关系 · ${escapeHtml(terms.length)} 条</summary>
        <div class="fold-body v2-term-list">
          ${terms.map((term) => `
            <article class="v2-term-row">
              <div class="v2-detail-topline"><strong>${escapeHtml(term.source_term || '未定')} → ${escapeHtml(term.target_term || '未定')}</strong><span class="summary-pill">${escapeHtml(term.relation_type || '未定')}</span></div>
              <p>${escapeHtml(term.relation_note || '')}</p>
              <details class="v2-raw-fold"><summary>term JSON</summary><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(term.data || {}), null, 2))}</pre></details>
            </article>
          `).join('')}
        </div>
      </details>
    `;
  }

  function renderTargetLocations(locations) {
    if (!locations?.length) {
      return '<div class="v2-detail-block"><span class="v2-detail-label">机器目标定位候选</span><p>没有显式《书名》标记；不自动补 target_work。</p></div>';
    }
    return `
      <details class="fold-card v2-raw-panel v2-target-location-fold">
        <summary>机器目标定位候选 · ${escapeHtml(locations.length)} 条</summary>
        <div class="fold-body v2-target-location-list">
          <p class="v2-evidence-note">以下仅是书名标记和 canonical passage 的机器候选，不能替代人工确认，也不等同于 quote_check 通过。</p>
          ${locations.map((location) => {
            const candidatePassage = location.target_passage_candidate;
            const candidateLocation = candidatePassage
              ? [candidatePassage.document_title, candidatePassage.section_title, candidatePassage.entry_title, `MD ${candidatePassage.md_line_start}-${candidatePassage.md_line_end}`].filter(Boolean).join(' · ')
              : '';
            return `
              <article class="v2-target-location-row">
                <div class="v2-detail-topline">
                  <strong>${escapeHtml(location.raw_label)}</strong>
                  <span class="summary-pill">${escapeHtml(statusLabel(location.work_identity_status))}</span>
                </div>
                <p>${escapeHtml(location.normalized_label)} · ${escapeHtml(statusLabel(location.target_passage_match_status))} · chars ${escapeHtml(location.label_start_char)}-${escapeHtml(location.label_end_char)}</p>
                ${candidatePassage ? `<p><strong>passage 候选</strong> ${escapeHtml(candidateLocation)} · <code>${escapeHtml(candidatePassage.passage_id)}</code></p>` : ''}
                <details class="v2-raw-fold"><summary>定位 provenance</summary><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(location.provenance || {}), null, 2))}</pre></details>
              </article>
            `;
          }).join('')}
        </div>
      </details>
    `;
  }

  function renderReviewEvents(events) {
    return `
      <details class="fold-card v2-raw-panel">
        <summary>人工审校事件 · ${escapeHtml(events?.length || 0)} 条</summary>
        <div class="fold-body">
          ${events?.length ? events.map((event) => `<article class="v2-review-row"><strong>${escapeHtml(event.review_status || 'pending')}</strong><span>${escapeHtml(event.reviewer || '未记录审校人')}</span><p>${escapeHtml(event.review_note || '')}</p><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(event.data || {}), null, 2))}</pre></article>`).join('') : '<p>当前尚无 review_events；human_status 仍为 pending。</p>'}
        </div>
      </details>
    `;
  }

  function renderResolutionEvents(events) {
    return `
      <details class="fold-card v2-raw-panel">
        <summary>外部来源解析事件 · ${escapeHtml(events?.length || 0)} 条</summary>
        <div class="fold-body">
          ${events?.length ? events.map((event) => `<article class="v2-review-row"><strong>${escapeHtml(event.resolution_kind || 'resolution')}</strong><span>${escapeHtml(event.to_queue_status || 'pending')} · ${escapeHtml(event.reviewer || '未记录审校人')}</span><p>${escapeHtml(event.resolution_note || '')}</p><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(event.data || {}), null, 2))}</pre></article>`).join('') : '<p>当前尚无外部来源解析事件；外部队列仍按 pending/candidate 状态处理。</p>'}
        </div>
      </details>
    `;
  }

  function organizeDetailSections(item) {
    const detail = elements.caseDetail;
    if (!detail || detail.querySelector('.v2-detail-groups')) return;

    const directNodes = Array.from(detail.children);
    const header = directNodes.find((node) => node.classList.contains('v2-detail-header'));
    const meta = directNodes.find((node) => node.classList.contains('v2-detail-meta'));
    const grid = directNodes.find((node) => node.classList.contains('v2-detail-grid'));
    const targetLocations = directNodes.find((node) => (
      node.classList.contains('v2-target-location-fold')
      || (node.classList.contains('v2-detail-block') && node.textContent.includes('机器目标定位候选'))
    ));
    const evidenceBlock = directNodes.find((node) => (
      node.classList.contains('v2-detail-block') && node.textContent.includes('证据层级')
    ));
    const summaryText = (node) => node.querySelector('summary')?.textContent?.trim() || '';
    const processFold = directNodes.find((node) => summaryText(node).includes('查看机器校验与五步过程'));
    const termsPanel = directNodes.find((node) => summaryText(node).startsWith('词项关系'));
    const reviewPanels = directNodes.filter((node) => summaryText(node).startsWith('人工审校事件'));
    const resolutionPanels = directNodes.filter((node) => summaryText(node).startsWith('外部来源解析事件'));
    const rawPanels = directNodes.filter((node) => (
      node.classList.contains('v2-raw-panel')
      && /machine_result JSON|human_review JSON|完整 annotation_case.v1 JSON/.test(summaryText(node))
    ));

    const makeSection = (title, badgeText, open) => {
      const section = document.createElement('details');
      section.className = 'v2-detail-section';
      section.open = open;
      const summary = document.createElement('summary');
      const heading = document.createElement('span');
      heading.textContent = title;
      const badge = document.createElement('span');
      badge.className = 'summary-pill';
      badge.textContent = badgeText;
      summary.append(heading, badge);
      const body = document.createElement('div');
      body.className = 'v2-detail-section-body';
      section.append(summary, body);
      return { section, body };
    };

    const groupOne = makeSection(
      '一、来源与定位',
      item.source_passage ? 'source passage 已定位' : 'source passage 待补',
      true,
    );
    const groupTwo = makeSection(
      '二、证据与过程',
      `${item.evidences?.length || 0} 条证据 · ${(item.process_steps || []).filter((step) => step.step_text).length} 步`,
      true,
    );
    const groupThree = makeSection('三、审校记录与原始数据', '按需展开', false);

    [meta, grid, targetLocations].filter(Boolean).forEach((node) => groupOne.body.appendChild(node));
    [evidenceBlock, processFold, termsPanel].filter(Boolean).forEach((node) => groupTwo.body.appendChild(node));
    [...reviewPanels, ...resolutionPanels, ...rawPanels].forEach((node) => groupThree.body.appendChild(node));

    const assigned = new Set([
      header,
      meta,
      grid,
      targetLocations,
      evidenceBlock,
      processFold,
      termsPanel,
      ...reviewPanels,
      ...resolutionPanels,
      ...rawPanels,
    ].filter(Boolean));
    directNodes.filter((node) => !assigned.has(node)).forEach((node) => groupThree.body.appendChild(node));

    detail.append(groupOne.section, groupTwo.section, groupThree.section);
  }

  function renderDetail(item) {
    const targetWorks = item.target_works?.length ? item.target_works.join('、') : '未明确';
    const targetScope = item.target_scope || {};
    const machineErrors = item.machine_result?.errors || item.machine_result?.validation_errors || [];
    const processSteps = (item.process_steps || []).filter((step) => step.step_text);
    const evidenceSummary = Object.entries(item.evidence_summary || {})
      .map(([key, value]) => `<span class="v2-resolution-chip ${escapeHtml(key)}">${escapeHtml(statusLabel(key))} ${escapeHtml(value)}</span>`)
      .join('');
    const provenance = item.provenance || {};
    const provenanceSource = provenance.source_file || provenance.source_text_file || '未记录';
    const provenanceExtra = [
      provenance.source_passage_id ? `passage ${provenance.source_passage_id}` : '',
      provenance.candidate_id ? `candidate ${provenance.candidate_id}` : '',
      provenance.legacy_case_id ? `legacy case ${provenance.legacy_case_id}` : '',
      provenance.model ? `model ${provenance.model}` : '',
    ].filter(Boolean).join(' · ');
    elements.caseDetail.innerHTML = `
      <div class="v2-detail-header">
        <p class="section-kicker">案例详情</p>
        <div class="v2-detail-topline">
          <h2>${escapeHtml(item.case_title)}</h2>
          <span class="v2-status-chip ${statusClass(item.machine_status)}">${escapeHtml(statusLabel(item.machine_status))}</span>
        </div>
        <p class="compact-note">${escapeHtml(item.case_id)} · ${escapeHtml(item.source_work)} · ${escapeHtml(item.origin)}</p>
        <div class="toolbar-actions">
          <a class="page-link" href="./annotation-workbench.html?case=${encodeURIComponent(item.case_id)}">开始五步 AI 审校</a>
        </div>
      </div>
      <div class="v2-detail-meta">
        <div class="v2-detail-block"><span class="v2-detail-label">机器状态</span><p>${escapeHtml(item.machine_status)} · lifecycle ${escapeHtml(item.lifecycle)}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">人工状态</span><p>${escapeHtml(item.human_status)} · review ${escapeHtml(item.review_status)}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">来源 / 再加工</span><p>${escapeHtml(item.origin)} · ${escapeHtml(provenance.transformation_kind || '未记录')}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">来源文件</span><p>${escapeHtml(provenanceSource)}</p>${provenanceExtra ? `<p>${escapeHtml(provenanceExtra)}</p>` : ''}</div>
        <div class="v2-detail-block"><span class="v2-detail-label">target_work</span><p>${escapeHtml(item.target_work || '未明确')}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">target_works / scope</span><p>${escapeHtml(targetWorks)} · ${escapeHtml(targetScope.status || 'unknown')}</p></div>
      </div>
      <div class="v2-detail-grid">
        ${renderPassage(item.source_passage, '机器识别的王氏来源段落')}
        ${renderPassage(item.target_passage, '机器识别的目标 passage')}
        <div class="v2-detail-block">
          <span class="v2-detail-label">目标文本</span>
          <h3>${escapeHtml(item.target_work || '目标典籍未明确')}</h3>
          <p>${escapeHtml(item.target_text || '—')}</p>
          ${item.evidence_state === 'source_no_citation' ? '<span class="v2-resolution-chip external_source_pending">source_no_citation：不制造 evidence</span>' : ''}
          ${targetScope.reason ? `<p class="v2-evidence-note">范围说明：${escapeHtml(targetScope.reason)}</p>` : ''}
        </div>
      </div>
      ${renderTargetLocations(item.target_location_candidates)}
      <div class="v2-detail-block">
        <div class="v2-detail-topline"><h3>证据层级</h3><span class="summary-pill">${escapeHtml(item.evidences?.length || 0)} 条</span></div>
        <div class="v2-evidence-meta">${evidenceSummary || '<span class="v2-resolution-chip unknown">无 evidence</span>'}</div>
        ${item.evidences?.length ? `
          <details class="fold-card v2-evidence-fold">
            <summary>展开全部 ${escapeHtml(item.evidences.length)} 条证据</summary>
            <div class="fold-body"><div class="v2-evidence-list">${item.evidences.map(renderEvidence).join('')}</div></div>
          </details>
        ` : '<p class="v2-empty-detail">该案例没有 evidence 记录。</p>'}
      </div>
      <details class="fold-card">
        <summary>查看机器校验与五步过程</summary>
        <div class="fold-body">
          <p><strong>机器校验错误/待办</strong>${machineErrors.length ? machineErrors.map((error) => `<span>${escapeHtml(error)}</span>`).join('') : '<span>无</span>'}</p>
          ${processSteps.length ? `<p><strong>过程步骤</strong></p><ol class="v2-step-list">${processSteps.map((step) => `<li><strong>${escapeHtml(step.field_name)}</strong>：${escapeHtml(step.step_text)}</li>`).join('')}</ol>` : '<p><strong>过程步骤</strong><span>暂无文本</span></p>'}
        </div>
      </details>
      ${renderTerms(item.terms)}
      ${renderReviewEvents(item.review_events)}
      ${renderResolutionEvents(item.resolution_events)}
      ${renderJsonPanel(item.machine_result, 'machine_result JSON')}
      ${renderJsonPanel(item.human_review, 'human_review JSON')}
      ${renderJsonPanel(item.case_data, '完整 annotation_case.v1 JSON')}
    `;
    organizeDetailSections(item);
  }

  async function selectCase(caseId) {
    if (!elements.caseDetail) return;
    state.selectedCaseId = caseId;
    renderCaseTable();
    elements.caseDetail.innerHTML = '<div class="v2-empty-detail">正在读取案例详情...</div>';
    try {
      const response = await requestJson(`/api/v2/case?id=${encodeURIComponent(caseId)}`);
      renderDetail(response);
    } catch (error) {
      elements.caseDetail.innerHTML = `<div class="v2-empty-detail">案例详情读取失败：${escapeHtml(error.message)}</div>`;
    }
  }

  function bindFilters() {
    let searchTimer = null;
    elements.caseTab?.addEventListener('click', () => setWorkspaceMode('browse'));
    elements.qualityTab?.addEventListener('click', () => setWorkspaceMode('quality'));
    window.addEventListener('hashchange', () => {
      const mode = window.location.hash.slice(1);
      setWorkspaceMode(mode, { updateUrl: mode === 'review' });
    });
    elements.search?.addEventListener('input', () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => loadCases({ resetPage: true }), 240);
    });
    [elements.sourceFilter, elements.machineFilter].filter(Boolean).forEach((element) => {
      element.addEventListener('change', () => loadCases({ resetPage: true }));
    });
    elements.pageSize?.addEventListener('change', () => {
      state.pageSize = Number(elements.pageSize.value) || 20;
      loadCases({ resetPage: true });
    });
    elements.previousPage?.addEventListener('click', () => {
      if (state.page > 1) {
        state.page -= 1;
        loadCases();
      }
    });
    elements.nextPage?.addEventListener('click', () => {
      if (state.page < state.pageCount) {
        state.page += 1;
        loadCases();
      }
    });
  }

  function populateSourceFilter(values) {
    if (!elements.sourceFilter) return;
    elements.sourceFilter.innerHTML = '<option value="all">全部来源</option>' + values
      .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
  }

  function buildCasesUrl() {
    const params = new URLSearchParams({
      page: String(state.page),
      pageSize: String(state.pageSize),
    });
    const query = String(elements.search.value || '').trim();
    const sourceWork = elements.sourceFilter?.value || 'all';
    const machineStatus = elements.machineFilter?.value || 'all';
    if (query) params.set('q', query);
    if (sourceWork !== 'all') params.set('source_work', sourceWork);
    if (machineStatus !== 'all') params.set('machine_status', machineStatus);
    return `/api/v2/cases?${params.toString()}`;
  }

  async function loadCases({ resetPage = false } = {}) {
    if (resetPage) state.page = 1;
    const requestId = ++state.requestId;
    elements.caseTable.innerHTML = '<p class="v2-empty-table">正在读取当前批次...</p>';
    try {
      const payload = await requestJson(buildCasesUrl());
      if (requestId !== state.requestId) return;
      state.cases = payload.items || [];
      state.totalCases = Number(payload.total ?? state.cases.length);
      state.page = Number(payload.page || state.page);
      state.pageSize = Number(payload.page_size || state.pageSize);
      state.pageCount = Number(payload.page_count || Math.max(1, Math.ceil(state.totalCases / state.pageSize)));
      renderCaseTable();
    } catch (error) {
      if (requestId !== state.requestId) return;
      elements.caseTable.innerHTML = `<p class="v2-empty-table">案例队列读取失败：${escapeHtml(error.message)}</p>`;
    }
  }

  async function init() {
    try {
      const [summary, cases] = await Promise.all([
        requestJson('/api/v2/summary'),
        requestJson(buildCasesUrl()),
      ]);
      state.summary = summary;
      state.cases = cases.items || [];
      state.totalCases = Number(cases.total ?? state.cases.length);
      state.page = Number(cases.page || 1);
      state.pageSize = Number(cases.page_size || state.pageSize);
      state.pageCount = Number(cases.page_count || Math.max(1, Math.ceil(state.totalCases / state.pageSize)));
      renderHero();
      renderOverall();
      renderMetrics();
      renderChecks();
      renderSources();
      renderReportContext();
      populateSourceFilter(cases.source_works || []);
      renderCaseTable();
      elements.status.textContent = `V2 工作库已连接 · 案例数据只读 · ${summary.database.display_path}`;
      if (elements.pageSize) elements.pageSize.value = String(state.pageSize);
      bindFilters();
      const initialCaseId = new URLSearchParams(window.location.search).get('case');
      const rawMode = window.location.hash.slice(1);
      const initialMode = initialCaseId ? 'browse' : rawMode || 'browse';
      setWorkspaceMode(initialMode, { updateUrl: rawMode === 'review' });
      if (initialCaseId) {
        selectCase(initialCaseId);
      }
    } catch (error) {
      elements.status.textContent = `V2 工作库连接失败：${error.message}`;
      elements.overall.className = 'v2-overall card fail';
      elements.overall.innerHTML = '<h2>无法读取 V2 工作库</h2><p>请确认本地 Node 服务已启动，并且 v2/data/real_runs/annotation_v2.db 存在。</p>';
    }
  }

  init();
})();

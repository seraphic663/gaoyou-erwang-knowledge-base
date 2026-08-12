const V2Acceptance = (() => {
  const detailedMode = document.body?.dataset.v2View !== 'display';
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
  };

  const labels = {
    machine_draft: 'machine draft',
    human_review: 'human review',
    gold: 'gold',
    rejected: 'rejected',
    draft: 'draft',
    pending: 'pending',
    approved: 'approved',
    uncertain: 'uncertain',
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

  function renderHero() {
    const summary = state.summary;
    if (!summary || !elements.heroMeta) return;
    const cards = [
      ['工作库', summary.database.display_path],
      ['来源文献', summary.counts.source_documents],
      ['候选层', summary.counts.candidate_items],
      ['案例', summary.counts.annotation_cases],
      ['总状态', summary.overall_status === 'pass_with_warnings' ? '通过（有待办）' : statusLabel(summary.overall_status)],
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
      <h2>${failed ? '当前不能交接' : warning ? '结构验收通过，但还有明确待办' : '可以交接'}</h2>
      <p>${failed ? '至少有一项数据库结构或引用完整性检查失败，请先处理失败项。' : '数据库可以作为机器工作库继续使用；人工审校、目标典籍补全和外部原典核验仍按待办推进。'}</p>
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
      ['候选层入库', summary.counts.candidate_items, '四部王氏原文机器候选'],
      ['案例入库', summary.counts.annotation_cases, '机器库记录'],
      ['机器草稿', summary.machine_status_counts.draft || 0, '结构基本可用，仍待核验'],
      ['人工 pending', summary.human_status_counts.pending || 0, '尚无 gold 晋级'],
      ['证据总数', summary.counts.annotation_evidences, '引文记录'],
      ['外部原典待核验', summary.evidence_counts.source_resolution.external_source_pending || 0, '尚未进入 canonical passage'],
    ];
    const detailedMetrics = [
      ['候选已生成案例', summary.candidate_output_case_count || 0, `其中 candidate shell ${summary.candidate_shell_case_count || 0} 条`],
      ['机器目标定位候选', summary.candidate_target_location_count || 0, '书名标记和片段命中，仍待人工确认'],
      ['canonical 目标标签', summary.candidate_target_canonical_count || 0, `其中 passage 候选 ${summary.candidate_target_passage_candidate_count || 0} 条`],
      ['机器拒绝', summary.machine_status_counts.rejected || 0, '仅表示显式结构不合格；target_work 未明确的案例保留 draft'],
      ['王氏正文二次命中', summary.evidence_counts.source_resolution.secondary_citation_match || 0, '不是原典核验通过'],
      ['外部来源登记', summary.counts.external_source_registry, '100 个唯一被引来源'],
      ['外部 canonical 底本', summary.report_context.external_source_inventory?.canonical_file_registered_count || 0, '当前本地尚未登记独立底本'],
      ['target_work 消歧队列', summary.counts.target_work_resolution_queue || 0, '机器候选或缺少上下文，待人工确认'],
      ['外部 edition 来源队列', summary.counts.external_source_resolution_queue || 0, '版本选择和底本登记待核'],
      ['外部 passage 引文队列', summary.counts.external_passage_resolution_queue || 0, '逐条 quote / location 待核'],
      ['人工审校队列', summary.report_context.work_queue_counts?.human_review_queue || summary.human_status_counts.pending || 0, `review_events ${summary.counts.review_events || 0}`],
      ['分批审校任务包', taskArtifacts.valid ? '覆盖通过' : '待重建', taskBatchText || '尚未生成稳定任务包'],
    ];
    const renderMetric = ([label, value, note]) => `
      <article class="card v2-metric">
        <small>${escapeHtml(label)}</small>
        <strong>${escapeHtml(String(value))}</strong>
        <small>${escapeHtml(note)}</small>
      </article>
    `;
    elements.metrics.innerHTML = detailedMode
      ? [...coreMetrics, ...detailedMetrics].map(renderMetric).join('')
      : coreMetrics.map(renderMetric).join('') + `
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
        <details class="v2-source-hash-fold">
          <summary>查看版本 hash</summary>
          <code class="v2-source-hash">sha256 ${escapeHtml(source.source_file_sha256)}</code>
        </details>
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
      ? `队列：target_work ${queueCounts.target_work_queue}；external passage ${queueCounts.external_passage_queue}；人工 ${queueCounts.human_review_queue}`
      : '';
    const taskManifest = context.review_task_manifest || {};
    const taskCounts = taskManifest.counts || {};
    const taskValidation = (taskManifest.coverage || {}).stream_validation || {};
    const taskText = Object.keys(taskCounts).length
      ? `任务包：case ${taskCounts.case_review || 0}/${taskValidation.case_review?.batch_count || 0} 批；target ${taskCounts.target_work_resolution || 0}/${taskValidation.target_work_resolution?.batch_count || 0} 批；external source ${taskCounts.external_source_resolution || 0}/${taskValidation.external_source_resolution?.batch_count || 0} 批；external passage ${taskCounts.external_passage_resolution || 0}/${taskValidation.external_passage_resolution?.batch_count || 0} 批`
      : '任务包：尚未生成';
    const locationText = `目标定位候选 ${state.summary.candidate_target_location_count || 0} 条；canonical 标签 ${state.summary.candidate_target_canonical_count || 0} 条；均未自动升级 target_work/target_passage`;
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
          <tr><th>案例</th><th>机器状态</th><th>目标典籍</th><th>目标定位候选</th><th>证据</th><th>人工状态</th></tr>
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
                    <small>${escapeHtml(item.case_id)} · ${escapeHtml(item.source_work)} · ${escapeHtml(item.source_entry_title || '未定位')}</small>
                  </div>
                </td>
                <td><span class="v2-status-chip ${statusClass(item.machine_status)}">${escapeHtml(statusLabel(item.machine_status))}</span><br /><small>${escapeHtml(item.lifecycle)}</small></td>
                <td>${escapeHtml(item.target_work || '未明确')}<br /><small>${escapeHtml(item.target_scope?.status || '')}</small></td>
                <td>${item.target_location_candidate_count ? `<span class="summary-pill">书名 ${escapeHtml(item.target_location_candidate_count)}</span><br /><small>canonical ${escapeHtml(item.target_location_canonical_count || 0)} · passage ${escapeHtml(item.target_location_passage_candidate_count || 0)}</small>` : '<small>无显式书名候选</small>'}</td>
                <td><div class="v2-evidence-meta">${resolutions || '<span class="v2-resolution-chip unknown">无 evidence</span>'}</div></td>
                <td><span class="v2-status-chip ${statusClass(item.human_status)}">${escapeHtml(statusLabel(item.human_status))}</span></td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
    elements.caseTable.querySelectorAll('tr[data-case-id]').forEach((row) => {
      row.addEventListener('click', () => {
        if (detailedMode) {
          selectCase(row.dataset.caseId);
        } else {
          window.location.href = `./v2-acceptance.html?case=${encodeURIComponent(row.dataset.caseId)}`;
        }
      });
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
    const secondaryText = location
      ? `王氏正文二次命中：${location.source_file?.split('/').pop() || ''} MD ${location.md_line_start}-${location.md_line_end}`
      : '';
    const externalText = evidence.external_cited_work
      ? `外部来源登记：${evidence.external_cited_work} · ${evidence.external_status || 'pending'}`
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
        ${detailedMode ? `<details class="v2-raw-fold"><summary>完整 evidence JSON</summary><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre></details>` : ''}
      </article>
    `;
  }

  function renderJsonPanel(value, label) {
    if (!detailedMode) return '';
    return `
      <details class="fold-card v2-raw-panel">
        <summary>${escapeHtml(label)}</summary>
        <div class="fold-body"><pre>${escapeHtml(JSON.stringify(value || {}, null, 2))}</pre></div>
      </details>
    `;
  }

  function renderTerms(terms) {
    if (!detailedMode) return '';
    if (!terms?.length) return '<div class="v2-detail-block"><span class="v2-detail-label">词项关系</span><p>无 annotation_terms 记录。</p></div>';
    return `
      <details class="fold-card v2-raw-panel">
        <summary>词项关系 · ${escapeHtml(terms.length)} 条</summary>
        <div class="fold-body v2-term-list">
          ${terms.map((term) => `
            <article class="v2-term-row">
              <div class="v2-detail-topline"><strong>${escapeHtml(term.source_term || '未定')} → ${escapeHtml(term.target_term || '未定')}</strong><span class="summary-pill">${escapeHtml(term.relation_type || '未定')}</span></div>
              <p>${escapeHtml(term.relation_note || '')}</p>
              <details class="v2-raw-fold"><summary>term JSON</summary><pre>${escapeHtml(JSON.stringify(term.data || {}, null, 2))}</pre></details>
            </article>
          `).join('')}
        </div>
      </details>
    `;
  }

  function renderTargetLocations(locations) {
    if (!detailedMode) return '';
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
                <details class="v2-raw-fold"><summary>定位 provenance</summary><pre>${escapeHtml(JSON.stringify(location.provenance || {}, null, 2))}</pre></details>
              </article>
            `;
          }).join('')}
        </div>
      </details>
    `;
  }

  function renderReviewEvents(events) {
    if (!detailedMode) return '';
    return `
      <details class="fold-card v2-raw-panel">
        <summary>人工审校事件 · ${escapeHtml(events?.length || 0)} 条</summary>
        <div class="fold-body">
          ${events?.length ? events.map((event) => `<article class="v2-review-row"><strong>${escapeHtml(event.review_status || 'pending')}</strong><span>${escapeHtml(event.reviewer || '未记录审校人')}</span><p>${escapeHtml(event.review_note || '')}</p><pre>${escapeHtml(JSON.stringify(event.data || {}, null, 2))}</pre></article>`).join('') : '<p>当前尚无 review_events；human_status 仍为 pending。</p>'}
        </div>
      </details>
    `;
  }

  function renderResolutionEvents(events) {
    if (!detailedMode) return '';
    return `
      <details class="fold-card v2-raw-panel">
        <summary>外部来源解析事件 · ${escapeHtml(events?.length || 0)} 条</summary>
        <div class="fold-body">
          ${events?.length ? events.map((event) => `<article class="v2-review-row"><strong>${escapeHtml(event.resolution_kind || 'resolution')}</strong><span>${escapeHtml(event.to_queue_status || 'pending')} · ${escapeHtml(event.reviewer || '未记录审校人')}</span><p>${escapeHtml(event.resolution_note || '')}</p><pre>${escapeHtml(JSON.stringify(event.data || {}, null, 2))}</pre></article>`).join('') : '<p>当前尚无外部来源解析事件；外部队列仍按 pending/candidate 状态处理。</p>'}
        </div>
      </details>
    `;
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
    const provenanceHash = provenance.source_file_sha256 || provenance.source_text_sha256 || '未记录';
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
      </div>
      <div class="v2-detail-meta">
        <div class="v2-detail-block"><span class="v2-detail-label">机器状态</span><p>${escapeHtml(item.machine_status)} · lifecycle ${escapeHtml(item.lifecycle)}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">人工状态</span><p>${escapeHtml(item.human_status)} · review ${escapeHtml(item.review_status)}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">来源 / 再加工</span><p>${escapeHtml(item.origin)} · ${escapeHtml(provenance.transformation_kind || '未记录')}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">来源文件</span><p>${escapeHtml(provenanceSource)}</p><code>${escapeHtml(provenanceHash)}</code>${provenanceExtra ? `<p>${escapeHtml(provenanceExtra)}</p>` : ''}</div>
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
        <summary>查看机器校验与过程</summary>
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
      elements.status.textContent = `V2 数据库已连接 · 只读 · ${summary.database.display_path}`;
      if (elements.pageSize) elements.pageSize.value = String(state.pageSize);
      bindFilters();
      const initialCaseId = new URLSearchParams(window.location.search).get('case');
      if (detailedMode && initialCaseId) selectCase(initialCaseId);
    } catch (error) {
      elements.status.textContent = `V2 数据库连接失败：${error.message}`;
      elements.overall.className = 'v2-overall card fail';
      elements.overall.innerHTML = '<h2>无法读取 V2 工作库</h2><p>请确认本地 Node 服务已启动，并且 v2/data/real_runs/annotation_v2.db 存在。</p>';
    }
  }

  init();
})();

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
    activeReviewTask: null,
    reviewWriteEnabled: false,
    reviewTaskResponse: null,
    reviewMessage: '',
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
    reviewTab: document.querySelector('#v2ReviewTab'),
    caseWorkspace: document.querySelector('#v2CaseWorkspace'),
    reviewWorkspace: document.querySelector('#v2ReviewWorkspace'),
    reviewWriteChip: document.querySelector('#v2ReviewWriteChip'),
    reviewStream: document.querySelector('#v2ReviewStream'),
    reviewBatch: document.querySelector('#v2ReviewBatch'),
    reviewDisplayLimit: document.querySelector('#v2ReviewDisplayLimit'),
    reviewLoadBatch: document.querySelector('#v2ReviewLoadBatch'),
    reviewTaskStatus: document.querySelector('#v2ReviewTaskStatus'),
    reviewSequence: document.querySelector('#v2ReviewSequence'),
    reviewTaskList: document.querySelector('#v2ReviewTaskList'),
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

  function setWorkspaceMode(mode = 'case') {
    const reviewMode = mode === 'review';
    if (elements.caseWorkspace) elements.caseWorkspace.hidden = reviewMode;
    if (elements.reviewWorkspace) elements.reviewWorkspace.hidden = !reviewMode;
    if (elements.caseTab) {
      elements.caseTab.classList.toggle('active', !reviewMode);
      elements.caseTab.setAttribute('aria-selected', String(!reviewMode));
    }
    if (elements.reviewTab) {
      elements.reviewTab.classList.toggle('active', reviewMode);
      elements.reviewTab.setAttribute('aria-selected', String(reviewMode));
    }
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
      ['目标候选边界', summary.candidate_target_automatic_promotion_count || 0, `自动升级 0；单一命中 ${summary.candidate_target_canonical_singleton_count || 0} · 歧义 ${summary.candidate_target_canonical_ambiguous_count || 0}`],
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
      ? `队列：target_work ${queueCounts.target_work_queue}；external passage ${queueCounts.external_passage_queue}；人工 ${queueCounts.human_review_queue}`
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

  function renderReviewSequence() {
    if (!elements.reviewSequence) return;
    const sequence = state.summary?.review_task_artifacts?.review_sequence || [];
    elements.reviewSequence.textContent = sequence.length
      ? `推荐顺序：${sequence.map((item) => `${item.phase}. ${item.label}`).join(' → ')}。无上下文候选壳自动留到最后，不影响前面可操作批次。`
      : '推荐顺序：外部来源 → 外部 passage → target_work → 案例字段。';
  }

  function reviewTaskCaseId(task) {
    if (task?.case_id) return String(task.case_id);
    if (task?.detail_ref?.case_id) return String(task.detail_ref.case_id);
    const evidence = task?.evidence_refs?.[0];
    return evidence?.case_id ? String(evidence.case_id) : '';
  }

  function reviewTaskLabel(task) {
    if (task.task_type === 'case_review') return task.case_title || task.case_id;
    if (task.task_type === 'target_work_resolution') return `${task.raw_label || '未定书名'} · ${task.case_id || ''}`;
    if (task.task_type === 'external_source_resolution') return task.cited_work || task.external_source_id;
    return `${task.cited_work || '外部 passage'} · ${task.quote || ''}`;
  }

  function renderStandaloneReviewTask(task) {
    if (!elements.caseDetail) return;
    const evidenceRefs = task.evidence_refs || [];
    const caseIds = [...new Set(evidenceRefs.map((entry) => entry.case_id).filter(Boolean))];
    const visibleEvidenceRefs = evidenceRefs.slice(0, 20);
    const evidenceMarkup = visibleEvidenceRefs.length
      ? visibleEvidenceRefs.map((entry) => `
          <article class="v2-evidence-card">
            <div class="v2-detail-topline">
              <strong>${escapeHtml(entry.cited_work || task.cited_work || '外部来源')}</strong>
              <span class="v2-resolution-chip ${escapeHtml(entry.queue_status || 'pending')}">${escapeHtml(statusLabel(entry.queue_status || 'pending'))}</span>
            </div>
            <p class="v2-evidence-note">${escapeHtml(entry.case_id || '未关联案例')} · evidence ${escapeHtml(entry.evidence_index)}</p>
            <div class="v2-evidence-quote">${escapeHtml(entry.quote || '（无引文）')}</div>
            <p class="v2-evidence-note">edition ${escapeHtml(entry.edition_status || 'missing')} · passage ${escapeHtml(entry.passage_status || 'missing')}</p>
          </article>
        `).join('')
      : '<p class="v2-empty-detail">该来源任务暂未附关联引文摘要。</p>';
    const moreEvidenceNote = evidenceRefs.length > visibleEvidenceRefs.length
      ? `<p class="compact-note">本任务共 ${evidenceRefs.length} 条引文，当前先显示 ${visibleEvidenceRefs.length} 条；完整任务数据仍保留在下方折叠区。</p>`
      : '';
    state.selectedCaseId = null;
    renderCaseTable();
    elements.caseDetail.innerHTML = `
      <div class="v2-detail-header">
        <p class="section-kicker">外部来源任务详情</p>
        <div class="v2-detail-topline">
          <h2>${escapeHtml(reviewTaskLabel(task))}</h2>
          <span class="v2-status-chip ${statusClass(task.queue_status || 'pending')}">${escapeHtml(statusLabel(task.queue_status || 'pending'))}</span>
        </div>
        <p class="compact-note">${escapeHtml(task.task_id)} · ${escapeHtml(task.external_source_id || '')}</p>
      </div>
      <div class="v2-detail-meta">
        <div class="v2-detail-block"><span class="v2-detail-label">外部来源</span><p>${escapeHtml(task.cited_work || '未注明典籍')}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">当前状态</span><p>${escapeHtml(task.queue_status || 'pending')} · edition ${escapeHtml(task.edition_status || 'missing')}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">底本文件</span><p>${escapeHtml(task.registered_source?.source_file || '尚未登记')}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">关联案例</span><p>${escapeHtml(caseIds.length ? caseIds.join('、') : '任务级来源，需先完成来源决定')}</p></div>
      </div>
      <div class="v2-detail-block">
        <div class="v2-detail-topline"><h3>关联引文摘要</h3><span class="summary-pill">${escapeHtml(evidenceRefs.length)} 条</span></div>
        <div class="v2-evidence-list">${evidenceMarkup}</div>
        ${moreEvidenceNote}
      </div>
      ${renderReviewForm({})}
      ${renderJsonPanel(task, '任务上下文 JSON')}
    `;
    elements.caseDetail.querySelector('#v2ReviewSubmit')?.addEventListener('click', submitActiveReview);
  }

  function renderReviewTaskList() {
    if (!elements.reviewTaskList || !state.reviewTaskResponse) return;
    const tasks = state.reviewTaskResponse.tasks || [];
    if (!tasks.length) {
      elements.reviewTaskList.innerHTML = '<p class="v2-empty-detail">该批次没有任务。</p>';
      return;
    }
    const limit = Math.max(1, Number(elements.reviewDisplayLimit?.value || 20));
    const visibleTasks = tasks.slice(0, limit);
    elements.reviewTaskList.innerHTML = visibleTasks.map((task) => `
      <article class="v2-review-task-row ${state.activeReviewTask?.task_id === task.task_id ? 'active' : ''}">
        <span class="v2-review-task-number">${escapeHtml(task.batch_position || '')}</span>
        <button class="v2-review-task-button" type="button" data-review-task-id="${escapeHtml(task.task_id)}">
          <strong>${escapeHtml(reviewTaskLabel(task))}</strong>
          <small>${escapeHtml(task.task_id)} · ${escapeHtml(task.queue_status || task.status?.human_status || '')}</small>
        </button>
        <span class="v2-status-chip ${statusClass(task.queue_status || task.status?.human_status || 'pending')}">${escapeHtml(statusLabel(task.queue_status || task.status?.human_status || 'pending'))}</span>
      </article>
    `).join('');
    if (tasks.length > visibleTasks.length) {
      elements.reviewTaskList.insertAdjacentHTML(
        'beforeend',
        `<p class="compact-note v2-review-list-note">本批共 ${tasks.length} 条，当前显示前 ${visibleTasks.length} 条；可调高“本屏显示”后继续查看。</p>`,
      );
    }
    elements.reviewTaskList.querySelectorAll('[data-review-task-id]').forEach((button) => {
      button.addEventListener('click', () => {
        const task = tasks.find((item) => item.task_id === button.dataset.reviewTaskId);
        if (!task) return;
        setWorkspaceMode('review');
        state.activeReviewTask = task;
        state.reviewMessage = '';
        renderReviewTaskList();
        const caseId = reviewTaskCaseId(task);
        if (caseId) {
          selectCase(caseId);
        } else if (elements.caseDetail) {
          renderStandaloneReviewTask(task);
        }
      });
    });
  }

  function updateReviewBatchOptions(batchCount, selectedBatch) {
    if (!elements.reviewBatch) return;
    const count = Math.max(0, Number(batchCount) || 0);
    elements.reviewBatch.innerHTML = count
      ? Array.from({ length: count }, (_, index) => {
        const number = index + 1;
        return `<option value="${number}"${number === Number(selectedBatch) ? ' selected' : ''}>第 ${number} / ${count} 批</option>`;
      }).join('')
      : '<option value="1">无批次</option>';
  }

  async function loadReviewTasks({ resetBatch = false } = {}) {
    if (!detailedMode || !elements.reviewTaskList) return;
    const stream = elements.reviewStream?.value || 'case_review';
    const batch = resetBatch ? 1 : Number(elements.reviewBatch?.value || 1);
    elements.reviewTaskStatus.textContent = '正在读取任务批次...';
    try {
      const response = await requestJson(`/api/v2/review-tasks?stream=${encodeURIComponent(stream)}&batch=${batch}`);
      state.reviewTaskResponse = response;
      state.reviewWriteEnabled = Boolean(response.write_enabled);
      updateReviewBatchOptions(response.batch_count, response.batch_number);
      const modeText = state.reviewWriteEnabled ? '本地写入开关已开启' : '只读；写入开关关闭';
      if (elements.reviewWriteChip) elements.reviewWriteChip.textContent = modeText;
      const displayLimit = Math.max(1, Number(elements.reviewDisplayLimit?.value || 20));
      elements.reviewTaskStatus.textContent = `${response.stream} · 第 ${response.batch_number}/${response.batch_count} 批 · 本批 ${response.task_count} 条，当前显示前 ${Math.min(displayLimit, response.task_count)} 条 · ${modeText}`;
      renderReviewTaskList();
    } catch (error) {
      elements.reviewTaskStatus.textContent = `任务包读取失败：${error.message}`;
      if (elements.reviewWriteChip) elements.reviewWriteChip.textContent = '任务包不可用';
      elements.reviewTaskList.innerHTML = '<p class="v2-empty-detail">无法读取当前任务包。</p>';
    }
  }

  function reviewCommonForm(task) {
    const reviewer = '';
    const operationId = `review-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return `
      <div class="v2-review-form-grid">
        <label>审校人（必填）<input id="v2ReviewReviewer" type="text" value="${escapeHtml(reviewer)}" placeholder="姓名或稳定 reviewer id" /></label>
        <label>operation_id（必填）<input id="v2ReviewOperationId" type="text" value="${escapeHtml(operationId)}" /></label>
        <label>当前任务类型<input type="text" value="${escapeHtml(task.task_type)}" disabled /></label>
        <label>任务状态<input type="text" value="${escapeHtml(task.queue_status || task.status?.human_status || 'pending')}" disabled /></label>
      </div>
      <label>审校说明<textarea id="v2ReviewNote" placeholder="记录本次决定依据；不填写学术结论时不要提交 approved。"></textarea></label>
    `;
  }

  function renderReviewForm(item) {
    if (!detailedMode || !state.activeReviewTask) return '';
    const task = state.activeReviewTask;
    const type = task.task_type;
    let body = '';
    let statuses = [];
    if (type === 'case_review') {
      statuses = ['uncertain', 'rejected', 'approved'];
      const fields = ['source_passage', 'target_work', 'target_passage', 'evidence', 'process', 'conclusion'];
      const evidence = item.evidences || [];
      body = `
        <label>案例审校状态<select id="v2ReviewStatus">${statuses.map((status) => `<option value="${status}">${escapeHtml(statusLabel(status))}</option>`).join('')}</select></label>
        <div>
          <p class="v2-detail-label">approved 所需字段决定（逐项勾选）</p>
          <div class="v2-review-decision-grid">${fields.map((field) => `<label class="v2-review-check"><input type="checkbox" data-review-field="${field}" />${escapeHtml(field)}</label>`).join('')}</div>
        </div>
        <div>
          <p class="v2-detail-label">approved 所需 evidence 决定（逐条勾选）</p>
          <div class="v2-review-decision-grid">${evidence.length ? evidence.map((entry) => `<label class="v2-review-check"><input type="checkbox" data-review-evidence="${entry.evidence_index}" />证据 ${escapeHtml(entry.evidence_index)}</label>`).join('') : '<span class="compact-note">无 evidence；请保持非 approved，除非你已明确补齐证据。</span>'}</div>
        </div>
        <label>案例字段 patch（高级；JSON）<textarea id="v2ReviewCasePatch">{}</textarea></label>
      `;
    } else if (type === 'target_work_resolution') {
      statuses = ['resolved', 'uncertain', 'rejected'];
      body = `
        <label>目标解析状态<select id="v2ReviewStatus">${statuses.map((status) => `<option value="${status}">${escapeHtml(statusLabel(status))}</option>`).join('')}</select></label>
        <label>target_work<input id="v2ReviewTargetWork" type="text" value="${escapeHtml(task.machine_candidate_work_key || '')}" placeholder="人工确认的典籍名" /></label>
        <label>target_passage_id<input id="v2ReviewTargetPassage" type="text" value="" placeholder="必须是 canonical passage 才能 resolved" /></label>
        <label>target_scope（JSON）<textarea id="v2ReviewTargetScope">${escapeHtml(JSON.stringify(task.case_context?.target_scope || { status: 'unresolved' }, null, 2))}</textarea></label>
      `;
    } else if (type === 'external_source_resolution') {
      statuses = ['candidate_available', 'no_public_match', 'verified', 'rejected'];
      const source = task.registered_source || {};
      body = `
        <label>外部来源状态<select id="v2ReviewStatus">${statuses.map((status) => `<option value="${status}">${escapeHtml(statusLabel(status))}</option>`).join('')}</select></label>
        <label>底本文件路径<input id="v2ReviewSourceFile" type="text" value="${escapeHtml(source.source_file || '')}" placeholder="verified 时填写可读取的文件路径" /></label>
        <label>版本/底本说明<input id="v2ReviewEdition" type="text" value="${escapeHtml(source.edition || '')}" /></label>
        <label>位置说明<input id="v2ReviewLocationNote" type="text" value="${escapeHtml(source.location_note || '')}" /></label>
        <p class="compact-note v2-review-inline-note">选择 verified 后，服务端会直接读取该文件并自动完成一致性核对；这里不再手填长串校验值。</p>
      `;
    } else {
      statuses = ['candidate_available', 'no_public_match', 'verified', 'rejected'];
      body = `
        <label>外部 passage 状态<select id="v2ReviewStatus">${statuses.map((status) => `<option value="${status}">${escapeHtml(statusLabel(status))}</option>`).join('')}</select></label>
        <label>selected_passage_id<input id="v2ReviewSelectedPassage" type="text" value="${escapeHtml(task.selected_passage_id || '')}" placeholder="verified 时必须是已核验 canonical passage" /></label>
      `;
    }
    const result = state.reviewMessage ? `<p class="v2-review-result ${state.reviewMessage.kind || ''}">${escapeHtml(state.reviewMessage.text)}</p>` : '';
    return `
      <section class="v2-review-form" data-review-task-type="${escapeHtml(type)}">
        <div class="v2-detail-topline"><h3>受控人工提交</h3><span class="summary-pill">${escapeHtml(task.task_id)}</span></div>
        <p class="compact-note">这一步只记录明确的人工作业。target/source/passage resolution 不会自动把案例升级为 gold；案例 approved 还必须通过完整字段、目标 passage 和 canonical quote 门。</p>
        ${reviewCommonForm(task)}
        <div class="v2-review-form-grid">${body}</div>
        <div class="v2-review-actions">
          <button id="v2ReviewSubmit" class="v2-review-submit-button" type="button"${state.reviewWriteEnabled ? '' : ' disabled'}>提交当前人工决定</button>
          <span class="v2-review-submit-result">${state.reviewWriteEnabled ? '写入开关已开启；提交后会产生 review_event/resolution_event。' : '当前只读；需以 V2_REVIEW_WRITE_ENABLED=1 启动本地服务后才能提交。'}</span>
        </div>
        ${result}
      </section>
    `;
  }

  function parseReviewJson(id, fallback = {}) {
    const element = document.querySelector(`#${id}`);
    if (!element || !String(element.value || '').trim()) return fallback;
    return JSON.parse(element.value);
  }

  async function submitActiveReview() {
    const task = state.activeReviewTask;
    if (!task) return;
    const resultElement = document.querySelector('.v2-review-submit-result');
    const reviewer = String(document.querySelector('#v2ReviewReviewer')?.value || '').trim();
    const operationId = String(document.querySelector('#v2ReviewOperationId')?.value || '').trim();
    const reviewNote = String(document.querySelector('#v2ReviewNote')?.value || '');
    const reviewStatus = String(document.querySelector('#v2ReviewStatus')?.value || '').trim();
    let payload;
    try {
      payload = {
        task_type: task.task_type,
        task_id: task.task_id,
        reviewer,
        operation_id: operationId,
        review_note: reviewNote,
      };
      if (task.task_type === 'case_review') {
        const fieldDecisions = {};
        document.querySelectorAll('[data-review-field]').forEach((input) => {
          fieldDecisions[input.dataset.reviewField] = input.checked ? 'approved' : 'pending';
        });
        const evidenceDecisions = [];
        document.querySelectorAll('[data-review-evidence]').forEach((input) => {
          evidenceDecisions.push({
            evidence_index: Number(input.dataset.reviewEvidence),
            status: input.checked ? 'approved' : 'pending',
          });
        });
        payload.case_id = task.case_id;
        payload.review_status = reviewStatus;
        payload.case_patch = parseReviewJson('v2ReviewCasePatch', {});
        payload.review = { field_decisions: fieldDecisions, evidence_decisions: evidenceDecisions };
      } else if (task.task_type === 'target_work_resolution') {
        payload.queue_item_id = task.queue_item_id;
        payload.resolution_status = reviewStatus;
        payload.target_work = document.querySelector('#v2ReviewTargetWork')?.value || '';
        payload.target_passage_id = document.querySelector('#v2ReviewTargetPassage')?.value || null;
        payload.target_scope = parseReviewJson('v2ReviewTargetScope', { status: 'unresolved' });
      } else if (task.task_type === 'external_source_resolution') {
        payload.queue_item_id = task.queue_item_id;
        payload.resolution_status = reviewStatus;
        payload.source_file = document.querySelector('#v2ReviewSourceFile')?.value || null;
        payload.edition = document.querySelector('#v2ReviewEdition')?.value || null;
        payload.location_note = document.querySelector('#v2ReviewLocationNote')?.value || null;
      } else {
        payload.queue_item_id = task.queue_item_id;
        payload.resolution_status = reviewStatus;
        payload.selected_passage_id = document.querySelector('#v2ReviewSelectedPassage')?.value || null;
      }
    } catch (error) {
      state.reviewMessage = { kind: 'fail', text: `提交未写入：表单 JSON 无效（${error.message}）` };
      if (resultElement) {
        resultElement.className = 'v2-review-submit-result fail';
        resultElement.textContent = state.reviewMessage.text;
      }
      return;
    }
    try {
      const response = await requestJson('/api/v2/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.reviewMessage = { kind: 'pass', text: `提交成功：${response.result?.operation_id || operationId}。任务包是静态快照，重建任务包后才会从待办列表移除。` };
      if (resultElement) resultElement.textContent = state.reviewMessage.text;
      const caseId = reviewTaskCaseId(task);
      if (caseId) await selectCase(caseId);
    } catch (error) {
      state.reviewMessage = { kind: 'fail', text: `提交未写入：${error.message}` };
      if (resultElement) {
        resultElement.className = 'v2-review-submit-result fail';
        resultElement.textContent = state.reviewMessage.text;
      }
    }
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
          <tr><th>案例</th><th>机器状态</th><th>目标典籍</th><th>证据</th><th>人工状态</th></tr>
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
          setWorkspaceMode('case');
          state.activeReviewTask = null;
          state.reviewMessage = '';
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
        ${detailedMode ? `<details class="v2-raw-fold"><summary>完整 evidence JSON</summary><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(data), null, 2))}</pre></details>` : ''}
      </article>
    `;
  }

  function renderJsonPanel(value, label) {
    if (!detailedMode) return '';
    return `
      <details class="fold-card v2-raw-panel">
        <summary>${escapeHtml(label)}</summary>
        <div class="fold-body"><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(value || {}), null, 2))}</pre></div>
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
              <details class="v2-raw-fold"><summary>term JSON</summary><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(term.data || {}), null, 2))}</pre></details>
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
                <details class="v2-raw-fold"><summary>定位 provenance</summary><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(location.provenance || {}), null, 2))}</pre></details>
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
          ${events?.length ? events.map((event) => `<article class="v2-review-row"><strong>${escapeHtml(event.review_status || 'pending')}</strong><span>${escapeHtml(event.reviewer || '未记录审校人')}</span><p>${escapeHtml(event.review_note || '')}</p><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(event.data || {}), null, 2))}</pre></article>`).join('') : '<p>当前尚无 review_events；human_status 仍为 pending。</p>'}
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
          ${events?.length ? events.map((event) => `<article class="v2-review-row"><strong>${escapeHtml(event.resolution_kind || 'resolution')}</strong><span>${escapeHtml(event.to_queue_status || 'pending')} · ${escapeHtml(event.reviewer || '未记录审校人')}</span><p>${escapeHtml(event.resolution_note || '')}</p><pre>${escapeHtml(JSON.stringify(stripInternalIdentityFields(event.data || {}), null, 2))}</pre></article>`).join('') : '<p>当前尚无外部来源解析事件；外部队列仍按 pending/candidate 状态处理。</p>'}
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
    const provenanceExtra = [
      provenance.source_passage_id ? `passage ${provenance.source_passage_id}` : '',
      provenance.candidate_id ? `candidate ${provenance.candidate_id}` : '',
      provenance.legacy_case_id ? `legacy case ${provenance.legacy_case_id}` : '',
      provenance.model ? `model ${provenance.model}` : '',
    ].filter(Boolean).join(' · ');
    const reviewForm = renderReviewForm(item);
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
      ${reviewForm}
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
    elements.caseDetail.querySelector('#v2ReviewSubmit')?.addEventListener('click', submitActiveReview);
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
    elements.caseTab?.addEventListener('click', () => setWorkspaceMode('case'));
    elements.reviewTab?.addEventListener('click', () => setWorkspaceMode('review'));
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
    elements.reviewStream?.addEventListener('change', () => loadReviewTasks({ resetBatch: true }));
    elements.reviewBatch?.addEventListener('change', () => loadReviewTasks());
    elements.reviewDisplayLimit?.addEventListener('change', () => {
      if (state.reviewTaskResponse) {
        const displayLimit = Math.max(1, Number(elements.reviewDisplayLimit.value || 20));
        elements.reviewTaskStatus.textContent = `${state.reviewTaskResponse.stream} · 第 ${state.reviewTaskResponse.batch_number}/${state.reviewTaskResponse.batch_count} 批 · 本批 ${state.reviewTaskResponse.task_count} 条，当前显示前 ${Math.min(displayLimit, state.reviewTaskResponse.task_count)} 条 · ${state.reviewWriteEnabled ? '本地写入开关已开启' : '只读；写入开关关闭'}`;
        renderReviewTaskList();
      }
    });
    elements.reviewLoadBatch?.addEventListener('click', () => loadReviewTasks());
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
      renderReviewSequence();
      populateSourceFilter(cases.source_works || []);
      renderCaseTable();
      elements.status.textContent = `V2 数据库已连接 · 只读 · ${summary.database.display_path}`;
      if (elements.pageSize) elements.pageSize.value = String(state.pageSize);
      bindFilters();
      setWorkspaceMode('case');
      if (detailedMode) loadReviewTasks({ resetBatch: true });
      const initialCaseId = new URLSearchParams(window.location.search).get('case');
      if (detailedMode && initialCaseId) {
        state.activeReviewTask = null;
        selectCase(initialCaseId);
      }
    } catch (error) {
      elements.status.textContent = `V2 数据库连接失败：${error.message}`;
      elements.overall.className = 'v2-overall card fail';
      elements.overall.innerHTML = '<h2>无法读取 V2 工作库</h2><p>请确认本地 Node 服务已启动，并且 v2/data/real_runs/annotation_v2.db 存在。</p>';
    }
  }

  init();
})();

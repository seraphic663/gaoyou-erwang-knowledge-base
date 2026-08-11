const V2Acceptance = (() => {
  const state = {
    summary: null,
    cases: [],
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
    const summary = state.summary;
    const metrics = [
      ['案例入库', summary.counts.annotation_cases, '机器库记录'],
      ['机器草稿', summary.machine_status_counts.draft || 0, '结构基本可用，仍待核验'],
      ['机器拒绝', summary.machine_status_counts.rejected || 0, '缺 target_work 或证据结构不完整'],
      ['人工 pending', summary.human_status_counts.pending || 0, '尚无 gold 晋级'],
      ['证据总数', summary.counts.annotation_evidences, '引文记录'],
      ['外部原典待核验', summary.evidence_counts.source_resolution.external_source_pending || 0, '尚未进入 canonical passage'],
      ['王氏正文二次命中', summary.evidence_counts.source_resolution.secondary_citation_match || 0, '不是原典核验通过'],
      ['外部来源登记', summary.counts.external_source_registry, '100 个唯一被引来源'],
    ];
    elements.metrics.innerHTML = metrics.map(([label, value, note]) => `
      <article class="card v2-metric">
        <small>${escapeHtml(label)}</small>
        <strong>${escapeHtml(String(value))}</strong>
        <small>${escapeHtml(note)}</small>
      </article>
    `).join('');
  }

  function renderChecks() {
    elements.checks.innerHTML = state.summary.checks.map((item) => `
      <article class="v2-check">
        <div class="v2-check-top">
          <strong>${escapeHtml(item.label)}</strong>
          <span class="v2-status-chip ${statusClass(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
        </div>
        <code>${escapeHtml(item.value)}</code>
        <p>${escapeHtml(item.detail)}</p>
      </article>
    `).join('');
  }

  function renderSources() {
    elements.sources.innerHTML = state.summary.sources.map((source) => `
      <article class="v2-source">
        <div class="v2-source-top">
          <strong>${escapeHtml(source.work_key)}</strong>
          <span class="v2-status-chip pass">唯一</span>
        </div>
        <p>${escapeHtml(source.source_file.split('/').pop() || source.source_file)}</p>
        <p>passage ${escapeHtml(source.passage_count)} · case ${escapeHtml(source.case_count)}</p>
        <code class="v2-source-hash" title="${escapeHtml(source.source_file_sha256)}">sha256 ${escapeHtml(source.source_file_sha256)}</code>
      </article>
    `).join('');
  }

  function renderReportContext() {
    const context = state.summary.report_context || {};
    const fullJson = Object.entries(context.full_json_context_counts || {})
      .map(([key, value]) => `${key} ${value}`)
      .join(' · ');
    elements.reportContext.textContent = fullJson
      ? `旧 full JSON 上下文命中（仅迁移线索）：${fullJson}`
      : '本页以 V2 数据库实时查询为准。';
  }

  function filteredCases() {
    const keyword = String(elements.search.value || '').trim().toLowerCase();
    const source = elements.sourceFilter.value;
    const machine = elements.machineFilter.value;
    return state.cases.filter((item) => {
      if (source !== 'all' && item.source_work !== source) return false;
      if (machine !== 'all' && item.machine_status !== machine) return false;
      if (!keyword) return true;
      return [
        item.case_id,
        item.case_title,
        item.source_work,
        item.target_work,
        ...(item.target_works || []),
        item.target_text,
        item.source_entry_title,
        item.lifecycle,
        item.machine_status,
      ].join(' ').toLowerCase().includes(keyword);
    });
  }

  function renderCaseTable() {
    const items = filteredCases();
    elements.caseCount.textContent = `显示 ${items.length} / ${state.cases.length}`;
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
      row.addEventListener('click', () => selectCase(row.dataset.caseId));
    });
  }

  function renderPassage(passage, label) {
    if (!passage) {
      return `<div class="v2-detail-block"><span class="v2-detail-label">${escapeHtml(label)}</span><p>未关联 passage</p></div>`;
    }
    const location = [passage.document_title, passage.section_title, passage.entry_title, `MD ${passage.md_line_start}-${passage.md_line_end}`]
      .filter(Boolean).join(' · ');
    return `
      <div class="v2-detail-block">
        <span class="v2-detail-label">${escapeHtml(label)}</span>
        <h3>${escapeHtml(location)}</h3>
        <code>${escapeHtml(passage.passage_id)}</code>
        <div class="v2-passage-text">${escapeHtml(passage.raw_text || passage.plain_text || '')}</div>
      </div>
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
      </article>
    `;
  }

  function renderDetail(item) {
    const targetWorks = item.target_works?.length ? item.target_works.join('、') : '未明确';
    const targetScope = item.target_scope || {};
    const machineErrors = item.machine_result?.errors || [];
    const processSteps = (item.process_steps || []).filter((step) => step.step_text);
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
        <div class="v2-detail-block"><span class="v2-detail-label">target_work</span><p>${escapeHtml(item.target_work || '未明确')}</p></div>
        <div class="v2-detail-block"><span class="v2-detail-label">target_works / scope</span><p>${escapeHtml(targetWorks)} · ${escapeHtml(targetScope.status || 'unknown')}</p></div>
      </div>
      <div class="v2-detail-grid">
        ${renderPassage(item.source_passage, '机器识别的王氏来源段落')}
        <div class="v2-detail-block">
          <span class="v2-detail-label">目标文本</span>
          <h3>${escapeHtml(item.target_work || '目标典籍未明确')}</h3>
          <p>${escapeHtml(item.target_text || '—')}</p>
          ${item.evidence_state === 'source_no_citation' ? '<span class="v2-resolution-chip external_source_pending">source_no_citation：不制造 evidence</span>' : ''}
          ${targetScope.reason ? `<p class="v2-evidence-note">范围说明：${escapeHtml(targetScope.reason)}</p>` : ''}
        </div>
      </div>
      <div class="v2-detail-block">
        <div class="v2-detail-topline"><h3>证据层级</h3><span class="summary-pill">${escapeHtml(item.evidences?.length || 0)} 条</span></div>
        <div class="v2-evidence-list">${item.evidences?.length ? item.evidences.map(renderEvidence).join('') : '<p class="v2-empty-detail">该案例没有 evidence 记录。</p>'}</div>
      </div>
      <details class="fold-card">
        <summary>查看机器校验与过程</summary>
        <div class="fold-body">
          <p><strong>机器校验错误/待办</strong>${machineErrors.length ? machineErrors.map((error) => `<span>${escapeHtml(error)}</span>`).join('') : '<span>无</span>'}</p>
          ${processSteps.length ? `<p><strong>过程步骤</strong></p><ol class="v2-step-list">${processSteps.map((step) => `<li><strong>${escapeHtml(step.field_name)}</strong>：${escapeHtml(step.step_text)}</li>`).join('')}</ol>` : '<p><strong>过程步骤</strong><span>暂无文本</span></p>'}
        </div>
      </details>
    `;
  }

  async function selectCase(caseId) {
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
    [elements.search, elements.sourceFilter, elements.machineFilter].forEach((element) => {
      element.addEventListener('input', renderCaseTable);
      element.addEventListener('change', renderCaseTable);
    });
  }

  function populateSourceFilter() {
    const values = [...new Set(state.cases.map((item) => item.source_work))];
    elements.sourceFilter.innerHTML = '<option value="all">全部来源</option>' + values
      .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
  }

  async function init() {
    try {
      const [summary, cases] = await Promise.all([
        requestJson('/api/v2/summary'),
        requestJson('/api/v2/cases'),
      ]);
      state.summary = summary;
      state.cases = cases.items || [];
      renderHero();
      renderOverall();
      renderMetrics();
      renderChecks();
      renderSources();
      renderReportContext();
      populateSourceFilter();
      renderCaseTable();
      elements.status.textContent = `V2 数据库已连接 · 只读 · ${summary.database.display_path}`;
      bindFilters();
    } catch (error) {
      elements.status.textContent = `V2 数据库连接失败：${error.message}`;
      elements.overall.className = 'v2-overall card fail';
      elements.overall.innerHTML = '<h2>无法读取 V2 工作库</h2><p>请确认本地 Node 服务已启动，并且 v2/data/real_runs/annotation_v2.db 存在。</p>';
    }
  }

  init();
})();

(() => {
  const STEP_DEFINITIONS = [
    { field: 'problem_discovery', label: '问题发现' },
    { field: 'research_question', label: '研究问题' },
    { field: 'evidence_collection', label: '证据收集' },
    { field: 'reasoning', label: '推理' },
    { field: 'conclusion', label: '结论' },
  ];
  const STATUS_LABELS = {
    pending: '待审',
    accepted: '认可',
    edited: '已修改',
    question: '存疑',
    reviewed: '已审阅',
    needs_revision: '退回修改',
    uncertain: '仍有疑问',
    active: '当前版本',
    superseded: '已被新版本替代',
    deleted: '已删除（可恢复）',
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
  };

  const el = {
    status: document.querySelector('#fiveStepStatus'),
    start: document.querySelector('#fiveStepStart'),
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
    cards: document.querySelector('#fiveStepCards'),
    reviewer: document.querySelector('#fiveStepReviewer'),
    decision: document.querySelector('#fiveStepDecision'),
    overallNote: document.querySelector('#fiveStepOverallNote'),
    save: document.querySelector('#fiveStepSave'),
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

  function renderSourceContext(item) {
    const passage = item.source_passage;
    const provenance = item.provenance || {};
    const passageText = plainText(passage);
    const evidenceCount = item.evidences?.length || 0;
    const sourceState = passage?.canonical_status || 'unknown';
    const evidenceSummary = Object.entries(item.evidence_summary || {})
      .map(([key, count]) => `${key} ${count}`)
      .join(' · ') || '暂无 evidence';
    el.sourceContext.innerHTML = `
      <article class="five-step-context-block">
        <h3>V2 来源段落</h3>
        <p class="five-step-context-meta">${escapeHtml(passage?.passage_id || item.source_passage_id || '未关联 passage')} · canonical ${escapeHtml(sourceState)} · ${escapeHtml(provenance.source_file || passage?.source_file || '来源路径未记录')}</p>
        <p class="five-step-context-text">${escapeHtml(passageText || 'V2 中未关联可展示的来源段落。')}</p>
      </article>
      <article class="five-step-context-block">
        <h3>证据与状态</h3>
        <p class="five-step-context-meta">${escapeHtml(evidenceCount)} 条 evidence · ${escapeHtml(evidenceSummary)}</p>
        <p>机器状态：${escapeHtml(item.machine_status || 'unknown')} · 人工状态：${escapeHtml(item.human_status || 'unknown')}</p>
        <p>来源：${escapeHtml(item.origin || provenance.source_format || '未记录')} · target_work：${escapeHtml(item.target_work || '未明确')}</p>
        <p class="compact-note">状态是 V2 当前记录，不代表原文、版本或引文已被人工核实。</p>
      </article>
    `;
  }

  function renderCase(item) {
    state.caseItem = item;
    el.caseTitle.textContent = item.case_title || '未命名案例';
    el.caseMeta.textContent = `${item.case_id} · ${item.source_work || '来源未注明'} · 机器 ${item.machine_status || 'unknown'} / 人工 ${item.human_status || 'unknown'}`;
    el.backLink.href = `./v2-database.html#browse`;
    renderSourceContext(item);
    el.case.hidden = false;
    el.controls.hidden = false;
    el.status.textContent = '已载入 V2 案例。确认所选案例和来源状态后，可生成五步草稿。';
  }

  function renderEvidenceRefs(step) {
    const refs = Array.isArray(step.evidence_refs) ? step.evidence_refs : [];
    if (!refs.length) {
      return '<p class="compact-note">AI 未指定可直接支撑本步的 V2 evidence；请人工判断是否缺证。</p>';
    }
    const evidenceByIndex = new Map((state.caseItem?.evidences || []).map((item) => [Number(item.evidence_index), item]));
    return `<div class="five-step-evidence-refs">${refs.map((index) => {
      const evidence = evidenceByIndex.get(Number(index));
      if (!evidence) return `<article class="five-step-evidence-ref">证据 ${escapeHtml(index)}：当前案例中找不到该编号，请核查。</article>`;
      const data = evidence.data || {};
      const status = [
        `quote ${evidence.quote_check || 'unchecked'}`,
        `source ${data.source_resolution || 'unknown'}`,
        `canonical ${evidence.source_passage?.canonical_status || 'unknown'}`,
      ].join(' · ');
      return `<article class="five-step-evidence-ref">
        <strong>证据 ${escapeHtml(evidence.evidence_index)} · ${escapeHtml(evidence.source_work || evidence.external_cited_work || '来源未注明')}</strong>
        <div class="five-step-context-meta">${escapeHtml(status)}</div>
        <blockquote>${escapeHtml(evidence.quote || '（无 quote）')}</blockquote>
      </article>`;
    }).join('')}</div>`;
  }

  function renderSteps() {
    if (!state.generation || !state.reviewedSteps.length) return;
    const draftByField = new Map(state.generation.draft.map((step) => [step.field, step]));
    el.cards.innerHTML = STEP_DEFINITIONS.map(({ field, label }, index) => {
      const draft = draftByField.get(field);
      const reviewed = state.reviewedSteps[index];
      const questions = draft.review_questions?.length
        ? `<ul>${draft.review_questions.map((question) => `<li>${escapeHtml(question)}</li>`).join('')}</ul>`
        : '<p class="compact-note">AI 未提出单独待核问题。</p>';
      return `
        <article class="five-step-step" data-step-field="${escapeHtml(field)}">
          <div class="five-step-step-heading"><span class="five-step-step-number">0${index + 1}</span><h3>${escapeHtml(label)}</h3></div>
          <div class="five-step-step-grid">
            <div>
              <p class="section-kicker">AI 草稿</p>
              <div class="five-step-ai-draft"><p>${escapeHtml(draft.text)}</p></div>
              ${renderEvidenceRefs(draft)}
              <div class="five-step-review-questions"><p class="section-kicker">AI 提醒核查</p>${questions}</div>
            </div>
            <div class="five-step-review-fields">
              <label>审校决定
                <select data-five-step-status="${escapeHtml(field)}">
                  <option value="pending"${reviewed.status === 'pending' ? ' selected' : ''}>请选择</option>
                  <option value="accepted"${reviewed.status === 'accepted' ? ' selected' : ''}>认可</option>
                  <option value="edited"${reviewed.status === 'edited' ? ' selected' : ''}>已修改</option>
                  <option value="question"${reviewed.status === 'question' ? ' selected' : ''}>存疑</option>
                </select>
              </label>
              <label>人工确认文本
                <textarea data-five-step-text="${escapeHtml(field)}" rows="6">${escapeHtml(reviewed.text)}</textarea>
              </label>
              <label>本步审校意见
                <textarea data-five-step-comment="${escapeHtml(field)}" rows="3" placeholder="指出保留、修改或存疑的理由">${escapeHtml(reviewed.comment)}</textarea>
              </label>
            </div>
          </div>
        </article>
      `;
    }).join('');
    updateSaveButton();
  }

  function generationSummary(generation) {
    const usage = generation.usage || {};
    const usageText = Number.isFinite(Number(usage.total_tokens)) ? ` · ${usage.total_tokens} tokens` : '';
    return `请求模型 ${generation.model_requested} · API 返回 ${generation.model_returned} · effort ${generation.reasoning_effort} · ${new Date(generation.generated_at).toLocaleString()}${usageText} · prompt ${generation.prompt_version}`;
  }

  function updateSaveButton() {
    const reviewer = el.reviewer?.value.trim() || '';
    const decisionsComplete = state.reviewedSteps.length === STEP_DEFINITIONS.length
      && state.reviewedSteps.every((step) => step.status !== 'pending' && step.text.trim()
        && (!['edited', 'question'].includes(step.status) || step.comment.trim()));
    el.save.disabled = !state.writeEnabled || !state.generation || !reviewer || !decisionsComplete || state.saving;
    if (state.writeEnabled) {
      el.writeStatus.textContent = '本地 V2 写入已开启；保存只追加审计记录，不更改案例状态。';
      el.writeStatus.classList.remove('five-step-write-disabled');
    } else {
      el.writeStatus.textContent = '当前只读。要保存审计意见，请在本地设置 V2_REVIEW_WRITE_ENABLED=1 后启动服务。';
      el.writeStatus.classList.add('five-step-write-disabled');
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
          <summary>${escapeHtml(record.submitted_at)} · ${escapeHtml(record.reviewer)} · ${escapeHtml(label)} · ${escapeHtml(record.model_requested)} / ${escapeHtml(record.reasoning_effort)} <span class="five-step-record-state ${stateClass}">${escapeHtml(stateLabel)}</span></summary>
          <div class="five-step-history-actions">${managementActions}</div>
          <p class="five-step-context-meta">版本 ${escapeHtml(record.record_version || 1)}${record.supersedes_audit_id ? ` · 修改自 ${escapeHtml(record.supersedes_audit_id)}` : ''}${record.superseded_by_audit_id ? ` · 新版本 ${escapeHtml(record.superseded_by_audit_id)}` : ''}</p>
          <p class="five-step-context-meta">API 返回 ${escapeHtml(record.model_returned)} · operation ${escapeHtml(record.operation_id)} · 来源指纹 ${escapeHtml(record.case_fingerprint)}</p>
          ${audit.overall_note ? `<p>${escapeHtml(audit.overall_note)}</p>` : ''}
          ${record.record_state === 'deleted' ? `<p class="five-step-context-meta">删除人：${escapeHtml(record.deleted_by || '未记录')} · ${escapeHtml(record.deleted_at || '')}${record.delete_reason ? ` · 原因：${escapeHtml(record.delete_reason)}` : ''}</p>` : ''}
          ${finalSteps.map((step, index) => `
            <div class="five-step-history-step">
              <strong>${escapeHtml(STEP_DEFINITIONS[index]?.label || step.field)} · ${escapeHtml(STATUS_LABELS[step.status] || step.status)}</strong>
              <p>${escapeHtml(step.text)}</p>
              ${step.comment ? `<p class="five-step-context-meta">审校意见：${escapeHtml(step.comment)}</p>` : ''}
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
      generated_at: record.generated_at,
      usage: audit.usage || null,
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
    el.save.textContent = '保存本次审计记录';
  }

  function cancelEditMode() {
    exitEditMode();
    state.generation = null;
    state.reviewedSteps = [];
    el.cards.innerHTML = '';
    el.form.hidden = true;
    el.generationMeta.hidden = true;
    el.saveMessage.textContent = '';
    updateSaveButton();
  }

  function managementActor() {
    const current = String(el.reviewer?.value || '').trim();
    if (current) return current;
    return String(window.prompt('请输入本次操作人姓名或 reviewer ID：') || '').trim();
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
    el.generate.textContent = '正在生成……';
    el.status.textContent = '正在读取所选 V2 案例并请求 DeepSeek……';
    el.saveMessage.textContent = '';
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
      state.editingAuditId = null;
      state.reviewedSteps = response.draft.map((step) => ({
        field: step.field,
        status: 'pending',
        text: step.text,
        comment: '',
      }));
      el.generationMeta.textContent = generationSummary(response);
      el.generationMeta.hidden = false;
      el.form.hidden = false;
      renderSteps();
      el.status.textContent = '五步草稿已生成。请逐步检查措辞、证据编号和来源核验状态。';
    } catch (error) {
      el.status.textContent = `生成失败：${error.message}`;
    } finally {
      state.generating = false;
      el.generate.disabled = false;
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

  async function submitAudit(event) {
    event.preventDefault();
    if (el.save.disabled || !state.generation) return;
    state.saving = true;
    updateSaveButton();
    el.saveMessage.className = 'five-step-save-message';
    el.saveMessage.textContent = '正在保存审计记录……';
    const operationId = globalThis.crypto?.randomUUID
      ? globalThis.crypto.randomUUID()
      : `five-step-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
    const editingAuditId = state.editingAuditId;
    const body = editingAuditId
      ? {
        audit_id: editingAuditId,
        case_id: state.caseId,
        reviewer: el.reviewer.value.trim(),
        operation_id: operationId,
        reviewed_steps: state.reviewedSteps,
        overall_decision: el.decision.value,
        overall_note: el.overallNote.value,
      }
      : {
        case_id: state.caseId,
        reviewer: el.reviewer.value.trim(),
        operation_id: operationId,
        case_fingerprint: state.generation.case_fingerprint,
        model_requested: state.generation.model_requested,
        model_returned: state.generation.model_returned,
        reasoning_effort: state.generation.reasoning_effort,
        prompt_version: state.generation.prompt_version,
        generated_at: state.generation.generated_at,
        usage: state.generation.usage,
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
        ? `修改已保存为新版本 ${payload.audit_id}。原版本仍保留。`
        : `已保存审计记录 ${payload.audit_id}。原案例与 human_status 未变。`;
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
      el.status.textContent = '请先从 V2 工作库选择要审校的案例。';
      el.start.hidden = false;
      return;
    }
    try {
      const item = await requestJson(`/api/v2/case?id=${encodeURIComponent(state.caseId)}`);
      renderCase(item);
      await loadHistory();
    } catch (error) {
      el.status.textContent = `无法打开该 V2 案例：${error.message}`;
      el.start.hidden = false;
    }
  }

  el.generate?.addEventListener('click', generateDraft);
  el.cancelEdit?.addEventListener('click', cancelEditMode);
  el.cards?.addEventListener('input', onStepInput);
  el.cards?.addEventListener('change', onStepInput);
  el.historyList?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-audit-action]');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    manageHistoryRecord(button.dataset.auditAction, button.dataset.auditId);
  });
  el.reviewer?.addEventListener('input', updateSaveButton);
  el.form?.addEventListener('submit', submitAudit);

  init();
})();

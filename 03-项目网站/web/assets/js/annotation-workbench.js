const WORKBENCH_STORAGE_KEY = 'gaoyou.annotationWorkbench.v1';
const TEMPLATE_PATTERN = /【(?:必填|建议|选填)】/;

const DOC_OPTIONS = [
  '广雅疏证_徐健怡.docx',
  '经传释词第二-㠯以已_李汶灿.docx',
  '读书杂志_平原之隰-譕臣_卢飞宇.docx',
  '其他'
];

const SOURCE_WORKS = ['广雅疏证', '经义述闻', '经传释词', '读书杂志'];
const TARGET_WORKS = ['左传', '管子', '尚书', '诗经', '尔雅', '周礼', '仪礼', '礼记', '论语', '其他'];
const RELATION_TYPES = ['', '训释', '校勘', '字际关系', '虚词用法', '句义解释', '未定'];
const RELATION_SUBTYPES = ['', '声转释义', '同义', '反训', '通假', '误字', '当作', '异文', '语法功能', '上下文解释', '未定'];
const EVIDENCE_ROLES = ['', '声训依据', '书证', '义证', '异文依据', '旧注辨驳', '反证', '支持校改', '上下文依据', '待定'];
const METHOD_CONCEPTS = ['声训', '书证', '义证', '异文校勘', '旧注辨驳', '比较互证', '语境释义', '虚词训释'];
const REVIEW_STATUSES = ['pending', 'approved', 'rejected', 'uncertain'];
const MACHINE_STATUSES = ['pending', 'draft', 'approved', 'rejected'];

const elements = {
  newDraftButton: document.querySelector('#newDraftButton'),
  deleteCurrentDraftButton: document.querySelector('#deleteCurrentDraftButton'),
  loadZaozhouButton: document.querySelector('#loadZaozhouButton'),
  loadPingyuanButton: document.querySelector('#loadPingyuanButton'),
  importJsonInput: document.querySelector('#importJsonInput'),
  draftSearchInput: document.querySelector('#draftSearchInput'),
  draftDocFilter: document.querySelector('#draftDocFilter'),
  draftIssueFilter: document.querySelector('#draftIssueFilter'),
  draftCountPill: document.querySelector('#draftCountPill'),
  draftList: document.querySelector('#draftList'),
  currentDraftTitle: document.querySelector('#currentDraftTitle'),
  qualitySummary: document.querySelector('#qualitySummary'),
  sourceExcerptInput: document.querySelector('#sourceExcerptInput'),
  addSelectedQuoteButton: document.querySelector('#addSelectedQuoteButton'),
  exportStatus: document.querySelector('#exportStatus'),
  downloadJsonButton: document.querySelector('#downloadJsonButton'),
  copyJsonButton: document.querySelector('#copyJsonButton'),
  form: document.querySelector('#workbenchForm')
};

const state = {
  drafts: [],
  currentId: '',
  filters: {
    query: '',
    doc: 'all',
    issue: 'all'
  }
};

function nowIso() {
  return new Date().toISOString();
}

function createId(prefix = 'draft') {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function emptyRelation() {
  return {
    source_term: '',
    target_term: '',
    relation_type: '',
    relation_subtype: '',
    relation_note: ''
  };
}

function emptyEvidence(quote = '') {
  return {
    quote,
    evidence_role: '',
    source_work: '',
    source_note: '',
    passage_id: null,
    quote_start_char: null,
    quote_end_char: null,
    quote_sha256: null,
    quote_check: 'unchecked'
  };
}

function emptyExpression(quote = '') {
  return {
    quote,
    passage_id: null,
    mapped_concepts: []
  };
}

function emptyCase() {
  const timestamp = nowIso();
  return {
    schema_version: 'annotation_case.v1',
    case_id: '',
    case_title: '',
    submitted_by: '',
    reviewed_by: '',
    source_work: '',
    source_passage_id: null,
    source_location: {
      work_title: '',
      section_title: '',
      entry_title: '',
      local_ordinal: null,
      archive_file_ref: ''
    },
    target_work: '',
    target_text: '',
    target_location: {
      chapter_or_section: '',
      raw_location_note: ''
    },
    term_relations: [emptyRelation()],
    evidences: [emptyEvidence()],
    problem_discovery: '',
    research_question: '',
    evidence_collection: '',
    reasoning: '',
    conclusion: '',
    method_profile: {
      concepts: [],
      expressions: []
    },
    machine_result: {
      status: 'pending',
      model: '',
      prompt_version: '',
      suggestions: [],
      confidence: null,
      validation: {
        quote_check: 'unchecked',
        schema_check: 'unchecked',
        enum_check: 'unchecked'
      }
    },
    human_review: {
      status: 'pending',
      reviewed_by: '',
      review_result: '',
      notes: ''
    },
    created_at: timestamp,
    updated_at: timestamp
  };
}

function createDraft(overrides = {}) {
  const caseData = {
    ...emptyCase(),
    ...(overrides.caseData || {})
  };

  return {
    id: createId(),
    doc_source: overrides.doc_source || '',
    source_excerpt: overrides.source_excerpt || '',
    caseData,
    created_at: caseData.created_at || nowIso(),
    updated_at: nowIso()
  };
}

function getCurrentDraft() {
  return state.drafts.find((draft) => draft.id === state.currentId) || state.drafts[0] || null;
}

function getCurrentCase() {
  return getCurrentDraft()?.caseData || null;
}

function saveState() {
  try {
    localStorage.setItem(WORKBENCH_STORAGE_KEY, JSON.stringify({
      drafts: state.drafts,
      currentId: state.currentId
    }));
  } catch (error) {
    console.warn('标注工作台自动保存失败', error);
  }
}

function loadState() {
  try {
    const raw = localStorage.getItem(WORKBENCH_STORAGE_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed.drafts)) return false;
    state.drafts = parsed.drafts.map(normalizeDraft);
    state.currentId = parsed.currentId || state.drafts[0]?.id || '';
    return state.drafts.length > 0;
  } catch (error) {
    console.warn('标注工作台读取本地草稿失败', error);
    return false;
  }
}

function normalizeDraft(draft) {
  const base = createDraft();
  const caseData = {
    ...base.caseData,
    ...(draft.caseData || draft || {})
  };
  caseData.source_location = {
    ...base.caseData.source_location,
    ...(caseData.source_location || {})
  };
  caseData.target_location = {
    ...base.caseData.target_location,
    ...(caseData.target_location || {})
  };
  caseData.term_relations = Array.isArray(caseData.term_relations) && caseData.term_relations.length
    ? caseData.term_relations
    : [emptyRelation()];
  caseData.evidences = Array.isArray(caseData.evidences) && caseData.evidences.length
    ? caseData.evidences
    : [emptyEvidence()];
  caseData.method_profile = {
    concepts: [],
    expressions: [],
    ...(caseData.method_profile || {})
  };
  caseData.method_profile.concepts = Array.isArray(caseData.method_profile.concepts) ? caseData.method_profile.concepts : [];
  caseData.method_profile.expressions = Array.isArray(caseData.method_profile.expressions) ? caseData.method_profile.expressions : [];
  caseData.machine_result = {
    ...base.caseData.machine_result,
    ...(caseData.machine_result || {})
  };
  caseData.machine_result.validation = {
    ...base.caseData.machine_result.validation,
    ...(caseData.machine_result.validation || {})
  };
  caseData.human_review = {
    ...base.caseData.human_review,
    ...(caseData.human_review || {})
  };

  return {
    id: draft.id || createId(),
    doc_source: draft.doc_source || '',
    source_excerpt: draft.source_excerpt || '',
    caseData,
    created_at: draft.created_at || caseData.created_at || nowIso(),
    updated_at: draft.updated_at || caseData.updated_at || nowIso()
  };
}

function markUpdated(draft) {
  const timestamp = nowIso();
  draft.updated_at = timestamp;
  draft.caseData.updated_at = timestamp;
  if (!draft.caseData.created_at) draft.caseData.created_at = draft.created_at || timestamp;
}

function getByPath(object, path) {
  return String(path).split('.').reduce((value, key) => (value == null ? value : value[key]), object);
}

function setByPath(object, path, value) {
  const parts = String(path).split('.');
  let cursor = object;
  parts.slice(0, -1).forEach((part) => {
    if (cursor[part] == null) cursor[part] = {};
    cursor = cursor[part];
  });
  cursor[parts[parts.length - 1]] = value;
}

function toNullOrText(value) {
  const text = String(value || '').trim();
  return text ? text : null;
}

function selectOptions(options, selected, placeholder = '') {
  const items = placeholder ? [placeholder, ...options] : options;
  return items.map((option) => {
    const value = option === placeholder ? '' : option;
    return `<option value="${escapeHtml(value)}"${value === selected ? ' selected' : ''}>${escapeHtml(option || '不确定')}</option>`;
  }).join('');
}

function fieldHtml({ label, path, value, help, type = 'text', placeholder = '', options = null, textarea = false, required = false }) {
  const requiredMark = required ? '<em>必填</em>' : '';
  const input = options
    ? `<select data-path="${escapeHtml(path)}">${selectOptions(options, value, placeholder)}</select>`
    : textarea
      ? `<textarea data-path="${escapeHtml(path)}" placeholder="${escapeHtml(placeholder)}">${escapeHtml(value || '')}</textarea>`
      : `<input data-path="${escapeHtml(path)}" type="${escapeHtml(type)}" value="${escapeHtml(value || '')}" placeholder="${escapeHtml(placeholder)}" />`;

  return `
    <label class="workbench-field">
      <span>${escapeHtml(label)}${requiredMark}</span>
      ${input}
      ${help ? `<small>${escapeHtml(help)}</small>` : ''}
    </label>
  `;
}

function renderDocFilter() {
  elements.draftDocFilter.innerHTML = [
    '<option value="all">全部 DOCX</option>',
    ...DOC_OPTIONS.map((doc) => `<option value="${escapeHtml(doc)}"${state.filters.doc === doc ? ' selected' : ''}>${escapeHtml(doc)}</option>`)
  ].join('');
}

function validationFor(draft) {
  const data = draft.caseData;
  const issues = [];
  const requiredChecks = [
    ['case_title', data.case_title],
    ['submitted_by', data.submitted_by],
    ['source_work', data.source_work],
    ['target_work', data.target_work],
    ['target_text', data.target_text],
    ['term_relations[].source_term', data.term_relations?.some((item) => String(item.source_term || '').trim())],
    ['term_relations[].target_term', data.term_relations?.some((item) => String(item.target_term || '').trim())],
    ['evidences[].quote', data.evidences?.some((item) => String(item.quote || '').trim())],
    ['conclusion', data.conclusion]
  ];

  requiredChecks.forEach(([label, value]) => {
    if (!value || (typeof value === 'string' && !value.trim())) {
      issues.push({ type: 'missing', message: `缺必填：${label}` });
    }
  });

  const serialized = JSON.stringify(data);
  if (TEMPLATE_PATTERN.test(serialized)) {
    issues.push({ type: 'template', message: '仍有【必填】/【建议】/【选填】模板标签' });
  }

  const sourceText = draft.source_excerpt || '';
  const quoteIssues = (data.evidences || [])
    .filter((item) => item.quote && sourceText && !sourceText.includes(item.quote));
  if (quoteIssues.length) {
    issues.push({ type: 'quote', message: `${quoteIssues.length} 条证据没有在材料摘录区严格匹配` });
  }

  if (!MACHINE_STATUSES.includes(data.machine_result?.status || 'pending')) {
    issues.push({ type: 'enum', message: 'machine_result.status 不在枚举中' });
  }

  if (!REVIEW_STATUSES.includes(data.human_review?.status || 'pending')) {
    issues.push({ type: 'enum', message: 'human_review.status 不在枚举中' });
  }

  return {
    issues,
    missing: issues.filter((item) => item.type === 'missing').length,
    template: issues.some((item) => item.type === 'template'),
    quote: issues.some((item) => item.type === 'quote'),
    ready: issues.filter((item) => ['missing', 'template', 'enum'].includes(item.type)).length === 0
  };
}

function draftMatchesFilters(draft) {
  const validation = validationFor(draft);
  const query = state.filters.query.trim().toLowerCase();
  const docMatch = state.filters.doc === 'all' || draft.doc_source === state.filters.doc;
  const issueMatch = state.filters.issue === 'all'
    || (state.filters.issue === 'missing' && validation.missing)
    || (state.filters.issue === 'template' && validation.template)
    || (state.filters.issue === 'quote' && validation.quote)
    || (state.filters.issue === 'ready' && validation.ready);
  const haystack = [
    draft.doc_source,
    draft.caseData.case_title,
    draft.caseData.source_work,
    draft.caseData.target_work,
    draft.caseData.target_text,
    draft.caseData.conclusion,
    ...(draft.caseData.evidences || []).map((item) => item.quote)
  ].join(' ').toLowerCase();
  const queryMatch = !query || haystack.includes(query);
  return docMatch && issueMatch && queryMatch;
}

function renderDraftList() {
  const drafts = state.drafts.filter(draftMatchesFilters);
  elements.draftCountPill.textContent = `${drafts.length}`;
  elements.draftList.innerHTML = drafts.length
    ? drafts.map((draft) => {
      const validation = validationFor(draft);
      const title = draft.caseData.case_title || '未命名案例';
      const stateLabel = validation.ready ? '可导出' : `缺 ${validation.missing}`;
      return `
        <div class="draft-list-item${draft.id === state.currentId ? ' active' : ''}">
          <button class="draft-select-button" type="button" data-action="select-draft" data-id="${escapeHtml(draft.id)}">
            <strong>${escapeHtml(title)}</strong>
            <span>${escapeHtml(draft.doc_source || '未选 DOCX')}</span>
            <em class="${validation.ready ? 'ready' : ''}">${escapeHtml(stateLabel)}</em>
          </button>
          <button class="draft-delete-button" type="button" data-action="delete-draft" data-id="${escapeHtml(draft.id)}" title="删除这个案例草稿">删除</button>
        </div>
      `;
    }).join('')
    : '<p class="compact-note">当前筛选下没有草稿。</p>';
}

function renderQuality() {
  const draft = getCurrentDraft();
  if (!draft) return;
  const validation = validationFor(draft);
  const evidenceCount = draft.caseData.evidences?.filter((item) => item.quote).length || 0;
  const relationCount = draft.caseData.term_relations?.filter((item) => item.source_term || item.target_term).length || 0;
  const methodCount = draft.caseData.method_profile?.concepts?.length || 0;
  elements.currentDraftTitle.textContent = draft.caseData.case_title || '未命名案例';
  elements.qualitySummary.innerHTML = [
    { label: '必填缺项', value: validation.missing, tone: validation.missing ? 'bad' : 'good' },
    { label: '证据', value: evidenceCount, tone: evidenceCount ? 'good' : 'bad' },
    { label: '字词关系', value: relationCount, tone: relationCount ? 'good' : 'bad' },
    { label: '方法标签', value: methodCount, tone: methodCount ? 'neutral' : 'warn' },
    { label: '导出状态', value: validation.ready ? '可导出' : '需补齐', tone: validation.ready ? 'good' : 'bad' }
  ].map((item) => `
    <div class="quality-card ${item.tone}">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
    </div>
  `).join('');

  const issueList = validation.issues.length
    ? validation.issues.map((item) => `<li>${escapeHtml(item.message)}</li>`).join('')
    : '<li>基础检查已通过。导出后仍需项目 validator 复核。</li>';
  elements.exportStatus.innerHTML = `<ul>${issueList}</ul>`;
}

function renderMethodConcepts(data) {
  const selected = new Set(data.method_profile?.concepts || []);
  return `
    <div class="concept-picker">
      ${METHOD_CONCEPTS.map((concept) => `
        <label class="concept-chip${selected.has(concept) ? ' active' : ''}">
          <input type="checkbox" data-concept="${escapeHtml(concept)}"${selected.has(concept) ? ' checked' : ''} />
          <span>${escapeHtml(concept)}</span>
        </label>
      `).join('')}
    </div>
  `;
}

function renderRelations(data) {
  return (data.term_relations || []).map((relation, index) => `
    <div class="repeat-card">
      <div class="repeat-head">
        <h4>字词关系 ${index + 1}</h4>
        <button class="plain-danger" type="button" data-action="remove-relation" data-index="${index}">删除</button>
      </div>
      <div class="workbench-field-grid">
        ${fieldHtml({ label: '原文对象', path: `term_relations.${index}.source_term`, value: relation.source_term, required: true, help: '被解释、被校、被讨论的字词。' })}
        ${fieldHtml({ label: '训释/校正对象', path: `term_relations.${index}.target_term`, value: relation.target_term, required: true, help: '解释后、校正后、对应的字词或义项。' })}
        ${fieldHtml({ label: '关系类型', path: `term_relations.${index}.relation_type`, value: relation.relation_type, options: RELATION_TYPES, help: '不确定可留空，审校者会定。' })}
        ${fieldHtml({ label: '二级关系', path: `term_relations.${index}.relation_subtype`, value: relation.relation_subtype, options: RELATION_SUBTYPES, help: '比一级关系更细。' })}
      </div>
      ${fieldHtml({ label: '关系说明', path: `term_relations.${index}.relation_note`, value: relation.relation_note, textarea: true, help: '解释 A 和 B 为什么这样关联。' })}
    </div>
  `).join('');
}

function renderEvidences(data) {
  return (data.evidences || []).map((evidence, index) => `
    <div class="repeat-card">
      <div class="repeat-head">
        <h4>证据 ${index + 1}</h4>
        <button class="plain-danger" type="button" data-action="remove-evidence" data-index="${index}">删除</button>
      </div>
      ${fieldHtml({ label: '证据引文', path: `evidences.${index}.quote`, value: evidence.quote, textarea: true, required: true, help: '忠实复制原文，不要意译。' })}
      <div class="workbench-field-grid">
        ${fieldHtml({ label: '证据作用', path: `evidences.${index}.evidence_role`, value: evidence.evidence_role, options: EVIDENCE_ROLES, help: '只说这一条证据在论证里的作用。' })}
        ${fieldHtml({ label: '证据来源', path: `evidences.${index}.source_work`, value: evidence.source_work, options: SOURCE_WORKS, placeholder: '可留空', help: '证据来自哪部书。' })}
      </div>
      ${fieldHtml({ label: '位置备注', path: `evidences.${index}.source_note`, value: evidence.source_note, help: '如李巡注、孙炎注、某卷某条。' })}
    </div>
  `).join('');
}

function renderExpressions(data) {
  const expressions = data.method_profile?.expressions || [];
  return expressions.map((expression, index) => `
    <div class="repeat-card">
      <div class="repeat-head">
        <h4>二王方法表达 ${index + 1}</h4>
        <button class="plain-danger" type="button" data-action="remove-expression" data-index="${index}">删除</button>
      </div>
      ${fieldHtml({ label: '原文表达', path: `method_profile.expressions.${index}.quote`, value: expression.quote, help: '如“一声之转”“读为”“当作”。' })}
      ${fieldHtml({ label: '对应现代方法', path: `method_profile.expressions.${index}.mapped_concepts_text`, value: (expression.mapped_concepts || []).join('、'), help: '多个用顿号分隔，如：声训、书证。' })}
    </div>
  `).join('') || '<p class="compact-note">不确定可以先不填，审校者或 AI 可后补。</p>';
}

function renderForm() {
  const draft = getCurrentDraft();
  if (!draft) {
    elements.form.innerHTML = '';
    return;
  }
  const data = draft.caseData;
  elements.sourceExcerptInput.value = draft.source_excerpt || '';

  elements.form.innerHTML = `
    <section class="card workbench-form-section">
      <div class="section-head compact-section-head">
        <p class="section-kicker">第一步</p>
        <h2>案例基本信息</h2>
      </div>
      <div class="workbench-field-grid">
        <label class="workbench-field">
          <span>来源 DOCX</span>
          <select data-draft-field="doc_source">${selectOptions(DOC_OPTIONS, draft.doc_source, '请选择 DOCX')}</select>
          <small>只用于本地管理草稿，不写入正式 JSON。</small>
        </label>
        ${fieldHtml({ label: '案例标题', path: 'case_title', value: data.case_title, required: true, placeholder: '如：造舟于河' })}
        ${fieldHtml({ label: '提交者', path: 'submitted_by', value: data.submitted_by, required: true, placeholder: 'human:你的名字' })}
        ${fieldHtml({ label: '二王出处', path: 'source_work', value: data.source_work, options: SOURCE_WORKS, required: true, placeholder: '请选择' })}
        ${fieldHtml({ label: '被考据作品', path: 'target_work', value: data.target_work, options: TARGET_WORKS, required: true, placeholder: '请选择' })}
        ${fieldHtml({ label: '被考据原文', path: 'target_text', value: data.target_text, required: true, placeholder: '复制 DOCX 或原文中的对象句' })}
      </div>
      <details class="fold-card workbench-help">
        <summary>可选位置信息</summary>
        <div class="fold-body">
          <div class="workbench-field-grid">
            ${fieldHtml({ label: '标题路径-篇章', path: 'source_location.section_title', value: data.source_location?.section_title })}
            ${fieldHtml({ label: '标题路径-条目', path: 'source_location.entry_title', value: data.source_location?.entry_title })}
            ${fieldHtml({ label: '对象位置', path: 'target_location.raw_location_note', value: data.target_location?.raw_location_note, placeholder: '如：左传昭公元年' })}
          </div>
        </div>
      </details>
    </section>

    <section class="card workbench-form-section">
      <div class="repeat-section-head">
        <div>
          <p class="section-kicker">第二步</p>
          <h2>字词关系</h2>
        </div>
        <button class="page-link page-link-muted toolbar-button" type="button" data-action="add-relation">新增关系</button>
      </div>
      ${renderRelations(data)}
    </section>

    <section class="card workbench-form-section">
      <div class="repeat-section-head">
        <div>
          <p class="section-kicker">第三步</p>
          <h2>证据</h2>
        </div>
        <button class="page-link page-link-muted toolbar-button" type="button" data-action="add-evidence">新增证据</button>
      </div>
      ${renderEvidences(data)}
    </section>

    <section class="card workbench-form-section">
      <div class="section-head compact-section-head">
        <p class="section-kicker">第四步</p>
        <h2>五步推理</h2>
      </div>
      <div class="workbench-field-grid process-grid">
        ${fieldHtml({ label: '发疑', path: 'problem_discovery', value: data.problem_discovery, textarea: true, help: '疑点从哪里来；不会写可以留空。' })}
        ${fieldHtml({ label: '设问', path: 'research_question', value: data.research_question, textarea: true, help: '把疑点改写成可验证问题。' })}
        ${fieldHtml({ label: '取证', path: 'evidence_collection', value: data.evidence_collection, textarea: true, help: '概括用了哪些材料。' })}
        ${fieldHtml({ label: '释理', path: 'reasoning', value: data.reasoning, textarea: true, help: '证据如何推出判断。' })}
        ${fieldHtml({ label: '结论', path: 'conclusion', value: data.conclusion, textarea: true, required: true, help: '一句话说明本案最终判断。' })}
      </div>
    </section>

    <section class="card workbench-form-section">
      <div class="repeat-section-head">
        <div>
          <p class="section-kicker">第五步</p>
          <h2>方法画像</h2>
        </div>
        <button class="page-link page-link-muted toolbar-button" type="button" data-action="add-expression">新增原文表达</button>
      </div>
      <div class="workbench-help-block">
        <strong>先分清：</strong>证据作用是一条证据在干什么；现代方法标签是整案用了什么方法。不会判断就先留空。
      </div>
      ${renderMethodConcepts(data)}
      ${renderExpressions(data)}
    </section>

    <section class="card workbench-form-section">
      <div class="section-head compact-section-head">
        <p class="section-kicker">审校占位</p>
        <h2>状态</h2>
      </div>
      <div class="workbench-field-grid">
        ${fieldHtml({ label: '机器状态', path: 'machine_result.status', value: data.machine_result?.status || 'pending', options: MACHINE_STATUSES })}
        ${fieldHtml({ label: '审校状态', path: 'human_review.status', value: data.human_review?.status || 'pending', options: REVIEW_STATUSES })}
        ${fieldHtml({ label: '审校者', path: 'human_review.reviewed_by', value: data.human_review?.reviewed_by || '', help: '成员初标一般留空。' })}
      </div>
    </section>
  `;
}

function renderAll() {
  renderDocFilter();
  renderDraftList();
  renderQuality();
  renderForm();
  saveState();
}

function updateCurrentFromInput(target) {
  const draft = getCurrentDraft();
  if (!draft) return;
  const path = target.dataset.path;
  const draftField = target.dataset.draftField;
  if (draftField) {
    draft[draftField] = target.value;
    if (draftField === 'doc_source' && !draft.caseData.source_location.archive_file_ref) {
      draft.caseData.source_location.archive_file_ref = target.value;
    }
  } else if (path) {
    if (path.endsWith('.mapped_concepts_text')) {
      const expressionPath = path.replace(/\.mapped_concepts_text$/, '');
      const expression = getByPath(draft.caseData, expressionPath);
      expression.mapped_concepts = target.value.split(/[、,，/／]/).map((item) => item.trim()).filter(Boolean);
    } else {
      setByPath(draft.caseData, path, target.value);
      if (path === 'human_review.reviewed_by') {
        draft.caseData.reviewed_by = target.value;
      }
    }
  }
  markUpdated(draft);
  renderDraftList();
  renderQuality();
  saveState();
}

function handleAction(action, target) {
  const draft = getCurrentDraft();
  if (!draft) return;
  const data = draft.caseData;
  const index = Number(target.dataset.index);
  if (action === 'add-relation') data.term_relations.push(emptyRelation());
  if (action === 'remove-relation' && data.term_relations.length > 1) data.term_relations.splice(index, 1);
  if (action === 'add-evidence') data.evidences.push(emptyEvidence());
  if (action === 'remove-evidence' && data.evidences.length > 1) data.evidences.splice(index, 1);
  if (action === 'add-expression') data.method_profile.expressions.push(emptyExpression());
  if (action === 'remove-expression') data.method_profile.expressions.splice(index, 1);
  markUpdated(draft);
  renderAll();
}

function addDraft(draft) {
  const normalized = normalizeDraft(draft);
  state.drafts.unshift(normalized);
  state.currentId = normalized.id;
  renderAll();
}

function setCurrentDraft(id) {
  state.currentId = id;
  renderAll();
}

function deleteDraft(id) {
  const draft = state.drafts.find((item) => item.id === id);
  if (!draft) return;
  const title = draft.caseData.case_title || '未命名案例';
  const confirmed = window.confirm(`确定删除“${title}”这个本机草稿吗？此操作只删除浏览器里的草稿，不会删除已经导出的 JSON 文件。`);
  if (!confirmed) return;

  state.drafts = state.drafts.filter((item) => item.id !== id);
  if (!state.drafts.length) {
    const blank = createDraft();
    state.drafts = [blank];
    state.currentId = blank.id;
  } else if (state.currentId === id) {
    state.currentId = state.drafts[0].id;
  }
  renderAll();
}

function addSelectedQuote() {
  const draft = getCurrentDraft();
  if (!draft) return;
  const input = elements.sourceExcerptInput;
  const quote = input.value.slice(input.selectionStart, input.selectionEnd).trim();
  if (!quote) {
    elements.exportStatus.innerHTML = '<ul><li>请先在材料摘录区选中一段证据原文。</li></ul>';
    return;
  }
  const emptySlot = draft.caseData.evidences.find((item) => !String(item.quote || '').trim());
  if (emptySlot) {
    emptySlot.quote = quote;
  } else {
    draft.caseData.evidences.push(emptyEvidence(quote));
  }
  markUpdated(draft);
  renderAll();
}

function cleanForExport(value) {
  if (Array.isArray(value)) return value.map(cleanForExport);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cleanForExport(item)]));
  }
  if (typeof value === 'string') return value.trim();
  return value;
}

async function sha256(text) {
  if (!window.crypto?.subtle) return null;
  const data = new TextEncoder().encode(text);
  const hash = await window.crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function buildExportCase() {
  const draft = getCurrentDraft();
  if (!draft) return null;
  const payload = cleanForExport(JSON.parse(JSON.stringify(draft.caseData)));
  payload.source_location.archive_file_ref = payload.source_location.archive_file_ref || draft.doc_source || '';
  payload.reviewed_by = payload.human_review?.reviewed_by || payload.reviewed_by || '';
  payload.term_relations = payload.term_relations.filter((item) => item.source_term || item.target_term || item.relation_note);
  payload.evidences = payload.evidences.filter((item) => item.quote || item.source_note);
  payload.method_profile.concepts = [...new Set(payload.method_profile.concepts || [])];
  payload.method_profile.expressions = (payload.method_profile.expressions || [])
    .filter((item) => item.quote || item.mapped_concepts?.length)
    .map((item) => ({
      quote: item.quote || '',
      passage_id: toNullOrText(item.passage_id),
      mapped_concepts: item.mapped_concepts || []
    }));

  for (const evidence of payload.evidences) {
    if (evidence.quote && !evidence.quote_sha256) {
      evidence.quote_sha256 = await sha256(evidence.quote);
    }
    if (evidence.quote && draft.source_excerpt) {
      evidence.quote_check = draft.source_excerpt.includes(evidence.quote) ? 'passed' : 'failed';
    }
  }

  return payload;
}

function filenameFor(payload) {
  const title = String(payload.case_title || '未命名案例')
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, '')
    .slice(0, 40) || 'annotation';
  const submitter = String(payload.submitted_by || 'unknown')
    .replace(/^human:/, '')
    .replace(/[\\/:*?"<>|\s]/g, '')
    .slice(0, 16) || 'unknown';
  return `${title}_${submitter}.annotation.json`;
}

async function downloadJson() {
  const payload = await buildExportCase();
  if (!payload) return;
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: 'application/json;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filenameFor(payload);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

async function copyJson() {
  const payload = await buildExportCase();
  if (!payload) return;
  const text = `${JSON.stringify(payload, null, 2)}\n`;
  await navigator.clipboard.writeText(text);
  elements.exportStatus.innerHTML = '<ul><li>JSON 已复制到剪贴板。</li></ul>';
}

function loadSample(kind) {
  const base = kind === 'pingyuan'
    ? createDraft({
      doc_source: '读书杂志_平原之隰-譕臣_卢飞宇.docx',
      source_excerpt: '平原之隰，奚有於高。言平隰之泽，虽有小封，不成于高。',
      caseData: {
        ...emptyCase(),
        case_title: '平原之隰',
        submitted_by: 'human:示例',
        source_work: '读书杂志',
        source_location: { ...emptyCase().source_location, archive_file_ref: '读书杂志_平原之隰-譕臣_卢飞宇.docx' },
        target_work: '管子',
        target_text: '平原之隰，奚有於高',
        term_relations: [{ source_term: '原', target_term: '封', relation_type: '校勘', relation_subtype: '误字', relation_note: '今本“原”疑当作“封”。' }],
        evidences: [emptyEvidence('言平隰之泽，虽有小封，不成于高。')],
        problem_discovery: '今本“平原之隰”与注文“小封”不协。',
        research_question: '是否应改读为“平隰之封”。',
        evidence_collection: '取《管子》注文与上下文为证。',
        reasoning: '由注文“小封”反证今本“原”字不协。',
        conclusion: '“平原之隰”疑当作“平隰之封”。',
        method_profile: { concepts: ['异文校勘', '书证', '义证'], expressions: [] },
        machine_result: emptyCase().machine_result,
        human_review: emptyCase().human_review,
        created_at: nowIso(),
        updated_at: nowIso()
      }
    })
    : createDraft({
      doc_source: '其他',
      source_excerpt: '造之言曹也，相比次之名也。造，次一声之转，故凡物之次谓之造。',
      caseData: {
        ...emptyCase(),
        case_title: '造舟于河',
        submitted_by: 'human:示例',
        source_work: '经义述闻',
        source_location: { ...emptyCase().source_location, section_title: '左传下', entry_title: '造舟于河', archive_file_ref: '经义述闻_王引之.md' },
        target_work: '左传',
        target_text: '造舟于河',
        target_location: { chapter_or_section: '昭公元年', raw_location_note: '左传昭公' },
        term_relations: [{ source_term: '造', target_term: '相比次', relation_type: '训释', relation_subtype: '声转释义', relation_note: '造、次一声之转。' }],
        evidences: [emptyEvidence('造，次一声之转')],
        problem_discovery: '旧注对“造舟”的解释不能稳定说明上下文。',
        research_question: '“造舟于河”的“造”是否应训为“相比次”。',
        evidence_collection: '取声音相转、旧注和文献用例为证。',
        reasoning: '造、次声近，且比舟为梁的文义相合。',
        conclusion: '“造舟于河”之“造”应训为比次、相比次。',
        method_profile: { concepts: ['声训', '书证', '旧注辨驳'], expressions: [emptyExpression('一声之转')] },
        machine_result: emptyCase().machine_result,
        human_review: emptyCase().human_review,
        created_at: nowIso(),
        updated_at: nowIso()
      }
    });

  addDraft(base);
}

function importJson(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const parsed = JSON.parse(reader.result);
      addDraft(createDraft({
        doc_source: parsed.source_location?.archive_file_ref || '',
        caseData: parsed
      }));
    } catch (error) {
      elements.exportStatus.innerHTML = `<ul><li>导入失败：${escapeHtml(error.message)}</li></ul>`;
    }
  };
  reader.readAsText(file, 'utf-8');
}

function bindEvents() {
  elements.newDraftButton?.addEventListener('click', () => addDraft(createDraft()));
  elements.deleteCurrentDraftButton?.addEventListener('click', () => {
    const draft = getCurrentDraft();
    if (draft) deleteDraft(draft.id);
  });
  elements.loadZaozhouButton?.addEventListener('click', () => loadSample('zaozhou'));
  elements.loadPingyuanButton?.addEventListener('click', () => loadSample('pingyuan'));
  elements.addSelectedQuoteButton?.addEventListener('click', addSelectedQuote);
  elements.downloadJsonButton?.addEventListener('click', downloadJson);
  elements.copyJsonButton?.addEventListener('click', copyJson);

  elements.importJsonInput?.addEventListener('change', (event) => {
    const [file] = event.target.files || [];
    if (file) importJson(file);
    event.target.value = '';
  });

  elements.draftSearchInput?.addEventListener('input', (event) => {
    state.filters.query = event.target.value;
    renderDraftList();
  });

  elements.draftDocFilter?.addEventListener('change', (event) => {
    state.filters.doc = event.target.value;
    renderDraftList();
  });

  elements.draftIssueFilter?.addEventListener('change', (event) => {
    state.filters.issue = event.target.value;
    renderDraftList();
  });

  elements.draftList?.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-action="select-draft"]');
    if (trigger) setCurrentDraft(trigger.dataset.id);
    const deleteTrigger = event.target.closest('[data-action="delete-draft"]');
    if (deleteTrigger) deleteDraft(deleteTrigger.dataset.id);
  });

  elements.sourceExcerptInput?.addEventListener('input', (event) => {
    const draft = getCurrentDraft();
    if (!draft) return;
    draft.source_excerpt = event.target.value;
    markUpdated(draft);
    renderQuality();
    saveState();
  });

  elements.form?.addEventListener('input', (event) => {
    if (event.target.matches('[data-path], [data-draft-field]')) updateCurrentFromInput(event.target);
  });

  elements.form?.addEventListener('change', (event) => {
    if (event.target.matches('[data-concept]')) {
      const draft = getCurrentDraft();
      if (!draft) return;
      const concept = event.target.dataset.concept;
      const concepts = new Set(draft.caseData.method_profile.concepts || []);
      if (event.target.checked) concepts.add(concept);
      else concepts.delete(concept);
      draft.caseData.method_profile.concepts = [...concepts];
      markUpdated(draft);
      renderAll();
      return;
    }
    if (event.target.matches('[data-path], [data-draft-field]')) updateCurrentFromInput(event.target);
  });

  elements.form?.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-action]');
    if (trigger) handleAction(trigger.dataset.action, trigger);
  });
}

function init() {
  const loaded = loadState();
  if (!loaded) {
    const draft = createDraft();
    state.drafts = [draft];
    state.currentId = draft.id;
  }
  if (!state.currentId && state.drafts.length) state.currentId = state.drafts[0].id;
  bindEvents();
  renderAll();
}

init();

/* The only translation boundary between the three case APIs and the UI.
 * Normalizers are pure: preserve identities and never modify source records. */
(function (root) {
  const stepLabels = {
    problem_discovery: '发疑',
    research_question: '设问',
    evidence_collection: '取证',
    reasoning: '释理',
    conclusion: '结论',
  };

  function locationText(location) {
    if (typeof location === 'string') return location;
    return (location?.title_path || []).join(' · ');
  }

  function passageView(label, passage) {
    if (!passage) return null;
    return {
      label,
      id: passage.passage_id,
      text: passage.raw_text || '',
      location: [passage.document_title, passage.section_title, passage.entry_title].filter(Boolean).join(' · '),
      raw: passage,
    };
  }

  const definitions = {
    main: {
      label: '主库材料',
      listEndpoint: '/api/browser',
      detailEndpoint: '/api/case',
      defaults: { view: 'cases', mode: 'fulltext', category: 'all' },
      filters: ['category', 'mode'],
      id: item => item.id,
      title: item => item.displayTitle || item.title,
      summary: item => item.problem || item.conclusion,
      origin: item => item.erwangWorkTitle,
      status: item => [item.status, item.certainty].filter(Boolean).join(' · '),
      unwrap: payload => payload,
      detail: item => ({
        problem: item.problem,
        claim: '',
        conclusion: item.conclusion,
        targetText: item.termLabel,
        sourceLocation: item.erwangLocation,
        targetLocation: [item.targetWorkTitle, item.targetLocation].filter(Boolean).join(' · '),
        methods: item.method,
        corpusQuery: { q: item.termNames?.[0] || item.title || '' },
        corpusLabel: '检索相关原文',
        terms: (item.terms || []).map(term => ({ id: term.id, label: term.term, relation: term.category })),
        evidence: (item.evidences || []).map(evidence => ({
          quote: evidence.quoteText || evidence.snippet || '',
          work: evidence.workTitle,
          kind: evidence.evidenceType,
          term: evidence.termId ? { id: evidence.termId, label: evidence.termName } : null,
          location: evidence.sourceLocation,
          note: evidence.note,
          status: '',
          raw: evidence,
        })),
        steps: item.processText ? [{ label: '考据过程', text: item.processText }] : [],
        passages: [],
        relatedCases: [],
      }),
    },
    annotation: {
      label: '人工标注材料',
      listEndpoint: '/api/annotation',
      detailEndpoint: '/api/annotation/detail',
      filters: ['document', 'method', 'annotator', 'origin'],
      id: item => item.id,
      title: item => item.case_title,
      summary: item => item.problem || item.target_text,
      origin: item => item.origin || item.source_work,
      status: item => [item.status, item.certainty].filter(Boolean).join(' · '),
      unwrap: payload => payload.item,
      detail: item => ({
        problem: item.problem,
        claim: item.claim,
        conclusion: item.conclusion,
        targetText: item.target_text,
        sourceLocation: item.source_document?.source_file_name,
        targetLocation: item.target_work,
        methods: (item.method_tags || []).join('、'),
        corpusQuery: { q: item.target_text || '' },
        corpusLabel: '检索相关原文',
        terms: (item.terms || []).map(term => ({
          label: [term.term, term.related_term].filter(Boolean).join(' → '),
          relation: term.relation_type,
          note: term.note,
        })),
        evidence: (item.evidences || []).map(evidence => ({
          quote: evidence.quote,
          work: evidence.work,
          kind: evidence.evidence_type,
          note: evidence.role,
          status: evidence.raw?.quote_check,
          raw: evidence,
        })),
        steps: (item.process_steps || []).map(step => ({ label: step.step_type, text: step.text })),
        passages: [],
        relatedCases: [],
      }),
    },
    v2: {
      label: 'V2 工作材料',
      listEndpoint: '/api/v2/cases',
      detailEndpoint: '/api/v2/case',
      filters: ['source_work', 'machine_status'],
      id: item => item.case_id,
      title: item => item.case_title,
      summary: item => item.target_text || item.source_excerpt,
      origin: item => item.source_work,
      status: item => [item.machine_status, item.human_status].filter(Boolean).join(' · '),
      unwrap: payload => payload,
      detail: item => ({
        problem: item.case_data?.problem_discovery,
        claim: item.case_data?.research_question,
        conclusion: item.case_data?.conclusion,
        targetText: item.target_text,
        sourceLocation: '',
        targetLocation: item.target_work,
        methods: '',
        corpusQuery: { case_id: item.case_id },
        corpusLabel: '查看本案原文与检索材料',
        terms: (item.terms || []).map(term => ({
          label: [term.source_term, term.target_term].filter(Boolean).join(' → '),
          relation: term.relation_type,
          note: term.relation_note,
        })),
        evidence: (item.evidences || []).map(evidence => ({
          quote: evidence.quote,
          work: evidence.source_work,
          kind: evidence.data?.evidence_role,
          location: locationText(evidence.data?.source_location),
          note: evidence.data?.relation_note || '',
          status: evidence.quote_check,
          raw: evidence,
        })),
        steps: (item.process_steps || []).map(step => ({
          label: stepLabels[step.field_name] || step.field_name,
          text: step.step_text,
        })),
        passages: [
          passageView('来源原文', item.source_passage),
          passageView('目标原文', item.target_passage),
        ].filter(Boolean),
        relatedCases: (item.related_cases || []).map(related => ({
          source: 'v2',
          id: related.case_id,
          title: related.case_title,
        })),
      }),
    },
  };

  function definition(source) {
    if (!Object.hasOwn(definitions, source)) throw new Error('未知案例来源');
    return definitions[source];
  }

  function summary(source, item) {
    const adapter = definition(source);
    return {
      source,
      sourceLabel: adapter.label,
      id: String(adapter.id(item)),
      title: adapter.title(item) || '未题名案例',
      summary: adapter.summary(item) || '',
      origin: adapter.origin(item) || '',
      status: adapter.status(item) || '待核',
    };
  }

  function detail(source, payload) {
    const adapter = definition(source);
    const item = adapter.unwrap(payload);
    if (!item || payload.ok === false) throw new Error('案例不存在');
    return { ...summary(source, item), ...adapter.detail(item), raw: item };
  }

  function list(source, payload) {
    return {
      items: (payload.items || []).map(item => summary(source, item)),
      total: Number(payload.total || 0),
      page: Number(payload.page || 1),
      pages: Number(source === 'v2' ? payload.page_count : payload.totalPages) || 1,
      sourceWorks: source === 'v2' ? payload.source_works || [] : [],
    };
  }

  function listUrl(source, params) {
    const adapter = definition(source);
    const query = new URLSearchParams({
      ...adapter.defaults,
      q: params.get('q') || '',
      page: params.get('page_' + source) || params.get('page') || '1',
      pageSize: '20',
    });
    for (const key of adapter.filters) {
      if (!params.has(key)) continue;
      query.delete(key);
      params.getAll(key).forEach(value => query.append(key, value));
    }
    return adapter.listEndpoint + '?' + query;
  }

  function detailUrl(source, id) {
    return definition(source).detailEndpoint + '?id=' + encodeURIComponent(id);
  }

  const sources = Object.freeze(Object.keys(definitions).map(id => Object.freeze({ id, label: definitions[id].label })));
  const api = { sources, summary, detail, list, listUrl, detailUrl };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CaseSources = api;
})(typeof window === 'undefined' ? globalThis : window);

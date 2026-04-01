const { STORE_DEFINITIONS } = require('../store-definitions');

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function parseJsonArray(value) {
  if (Array.isArray(value)) {
    return value;
  }

  if (typeof value !== 'string' || !value.trim()) {
    return [];
  }

  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function trimText(value, maxLength = 64) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) {
    return '';
  }

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength - 1)}…`;
}

function normalizeKeyword(value) {
  return String(value || '').trim().toLowerCase();
}

function summarizeTermNames(termNames) {
  const names = termNames.filter(Boolean);
  if (!names.length) {
    return '未单独关联';
  }

  if (names.length <= 3) {
    return names.join('、');
  }

  return `${names.slice(0, 3).join('、')} 等${names.length}项`;
}

function buildCaseDisplay(title, sectionTitle, volumeTitle) {
  const rawTitle = String(title || '').trim();
  const groupedTitle = /^广雅疏证「(.+?也)」词条群（行(\d+)）$/.exec(rawTitle);

  if (groupedTitle) {
    return {
      displayTitle: `《广雅疏证》「${groupedTitle[1]}」条`,
      displaySubtitle: [sectionTitle || '释诂', `行${groupedTitle[2]}`].filter(Boolean).join(' · '),
    };
  }

  return {
    displayTitle: rawTitle || '未命名案例',
    displaySubtitle: [sectionTitle, volumeTitle].filter(Boolean).join(' · '),
  };
}

function buildCounts(snapshot) {
  return Object.fromEntries(
    Object.entries(snapshot.tables || {}).map(([name, records]) => [name, safeArray(records).length]),
  );
}

function buildStores(counts) {
  return STORE_DEFINITIONS.map((definition) => ({
    ...definition,
    count: counts[definition.name] || 0,
  }));
}

function buildLocation(passage) {
  if (!passage) {
    return '';
  }

  return [passage.juan, passage.chapter, passage.location_note].filter(Boolean).join(' · ');
}

function buildContext(snapshot) {
  const works = safeArray(snapshot.tables?.works);
  const passages = safeArray(snapshot.tables?.passages);
  const terms = safeArray(snapshot.tables?.terms);
  const cases = safeArray(snapshot.tables?.cases);
  const evidences = safeArray(snapshot.tables?.evidences);

  const workMap = new Map(works.map((item) => [item.id, item]));
  const passageMap = new Map(passages.map((item) => [item.id, item]));
  const termMap = new Map(terms.map((item) => [item.id, item]));
  const caseMap = new Map(cases.map((item) => [item.id, item]));
  const evidenceByCase = new Map();

  evidences.forEach((item) => {
    const bucket = evidenceByCase.get(item.case_id) || [];
    bucket.push(item);
    evidenceByCase.set(item.case_id, bucket);
  });

  return {
    snapshot,
    counts: buildCounts(snapshot),
    workMap,
    passageMap,
    termMap,
    caseMap,
    evidenceByCase,
    cases,
    terms,
  };
}

function normalizeTerm(item) {
  return {
    id: item.id,
    term: item.term,
    term_type: item.term_type,
    category: item.category,
    aliases: parseJsonArray(item.aliases),
    notes: item.notes || '',
    core_meaning: item.core_meaning || '',
    case_ids: parseJsonArray(item.case_ids),
  };
}

function enrichCase(context, caseRecord) {
  const termIds = parseJsonArray(caseRecord.term_ids);
  const termNames = termIds
    .map((termId) => context.termMap.get(termId)?.term || '')
    .filter(Boolean);
  const display = buildCaseDisplay(caseRecord.title, caseRecord.section_title, caseRecord.volume_title);

  const erwangPassage = context.passageMap.get(caseRecord.erwang_passage_id) || null;
  const targetPassage = context.passageMap.get(caseRecord.target_passage_id) || null;
  const erwangWork = erwangPassage ? context.workMap.get(erwangPassage.work_id) : null;
  const targetWork = targetPassage ? context.workMap.get(targetPassage.work_id) : null;
  const evidences = context.evidenceByCase.get(caseRecord.id) || [];
  const evidenceQuotes = evidences
    .map((item) => item.core_snippet || item.quote_text || '')
    .filter(Boolean)
    .slice(0, 2)
    .map((item) => trimText(item, 56));

  return {
    id: caseRecord.id,
    title: caseRecord.title,
    displayTitle: display.displayTitle,
    displaySubtitle: display.displaySubtitle,
    sectionTitle: caseRecord.section_title || '',
    volumeTitle: caseRecord.volume_title || '',
    termIds,
    termNames,
    termName: termNames[0] || '',
    termLabel: summarizeTermNames(termNames),
    erwangPassageId: caseRecord.erwang_passage_id || null,
    targetPassageId: caseRecord.target_passage_id || null,
    erwangWorkTitle: erwangWork?.title || (caseRecord.volume_title ? '广雅疏证' : ''),
    targetWorkTitle: targetWork?.title || '',
    erwangLocation: buildLocation(erwangPassage) || caseRecord.volume_title || caseRecord.section_title || '',
    targetLocation: buildLocation(targetPassage),
    problem: caseRecord.problem || '',
    method: caseRecord.method || '',
    processText: caseRecord.process_text || '',
    conclusion: caseRecord.conclusion || '',
    certainty: caseRecord.certainty || '',
    status: caseRecord.status || '',
    evidenceCount: evidences.length,
    evidenceQuotes,
  };
}

function enrichEvidence(context, evidenceRecord) {
  const work = evidenceRecord.work_id ? context.workMap.get(evidenceRecord.work_id) : null;
  const passage = evidenceRecord.source_passage_id ? context.passageMap.get(evidenceRecord.source_passage_id) : null;
  const term = evidenceRecord.term_id ? context.termMap.get(evidenceRecord.term_id) : null;
  const caseRecord = context.caseMap.get(evidenceRecord.case_id) || null;
  const caseDisplay = caseRecord
    ? buildCaseDisplay(caseRecord.title, caseRecord.section_title, caseRecord.volume_title)
    : { displayTitle: '', displaySubtitle: '' };

  return {
    id: evidenceRecord.id,
    caseId: evidenceRecord.case_id,
    caseTitle: caseDisplay.displayTitle,
    caseSubtitle: caseDisplay.displaySubtitle,
    termId: evidenceRecord.term_id || null,
    termName: term?.term || '',
    workId: evidenceRecord.work_id || null,
    workTitle: work?.title || '',
    sourcePassageId: evidenceRecord.source_passage_id || null,
    sourceLocation: buildLocation(passage),
    evidenceType: evidenceRecord.evidence_type || '',
    snippet: evidenceRecord.core_snippet || evidenceRecord.quote_text || '',
    quoteText: evidenceRecord.quote_text || '',
    note: evidenceRecord.note || '',
  };
}

function buildTermCard(context, termRecord) {
  const aliases = parseJsonArray(termRecord.aliases);
  const caseIds = parseJsonArray(termRecord.case_ids);
  const relatedCases = caseIds
    .map((caseId) => context.caseMap.get(caseId))
    .filter(Boolean)
    .slice(0, 3)
    .map((item) => {
      const display = buildCaseDisplay(item.title, item.section_title, item.volume_title);
      return {
        id: item.id,
        displayTitle: display.displayTitle,
      };
    });

  return {
    id: termRecord.id,
    term: termRecord.term,
    termType: termRecord.term_type || '',
    category: termRecord.category || '',
    aliases,
    notes: termRecord.notes || '',
    coreMeaning: termRecord.core_meaning || '',
    caseCount: caseIds.length,
    relatedCases,
  };
}

function buildBrowserTermItem(context, termRecord) {
  const card = buildTermCard(context, termRecord);

  return {
    ...card,
    preview: trimText(termRecord.core_meaning || termRecord.notes || '', 88),
    searchEntry: [termRecord.term, termRecord.term_type, termRecord.category, ...card.aliases].join(' '),
    searchFulltext: [termRecord.term, termRecord.term_type, termRecord.category, ...card.aliases, termRecord.core_meaning || '', termRecord.notes || ''].join(' '),
  };
}

function buildBrowserCaseItem(context, caseRecord) {
  const detail = enrichCase(context, caseRecord);

  return {
    ...detail,
    preview: trimText(detail.conclusion || detail.problem || detail.processText || '', 108),
    searchEntry: [
      detail.displayTitle,
      detail.displaySubtitle,
      detail.termLabel,
      detail.termNames.join(' '),
      detail.sectionTitle,
      detail.method,
    ].join(' '),
    searchFulltext: [
      detail.displayTitle,
      detail.displaySubtitle,
      detail.termLabel,
      detail.termNames.join(' '),
      detail.problem,
      detail.processText,
      detail.conclusion,
      detail.erwangWorkTitle,
      detail.targetWorkTitle,
      detail.erwangLocation,
      detail.targetLocation,
      detail.evidenceQuotes.join(' '),
    ].join(' '),
  };
}

function buildCategoryBuckets(items, pickValue) {
  const bucketMap = new Map();

  items.forEach((item) => {
    const value = pickValue(item) || '未分类';
    bucketMap.set(value, (bucketMap.get(value) || 0) + 1);
  });

  return [...bucketMap.entries()]
    .map(([value, count]) => ({ value, label: value, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-CN'));
}

function buildTermDetail(context, termId) {
  const normalizedId = Number(termId);
  const termRecord = context.termMap.get(normalizedId);
  if (!termRecord) {
    return null;
  }

  const card = buildTermCard(context, termRecord);
  const caseIds = parseJsonArray(termRecord.case_ids);
  const relatedCases = caseIds
    .map((caseId) => context.caseMap.get(caseId))
    .filter(Boolean)
    .map((item) => enrichCase(context, item));
  const evidences = safeArray(context.snapshot.tables?.evidences)
    .filter((item) => item.term_id === normalizedId)
    .map((item) => enrichEvidence(context, item));
  const relatedWorks = [...new Set(evidences.map((item) => item.workTitle).filter(Boolean))];
  const evidenceTypes = [...new Set(evidences.map((item) => item.evidenceType).filter(Boolean))];

  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    id: card.id,
    term: card.term,
    termType: card.termType,
    category: card.category,
    aliases: card.aliases,
    notes: termRecord.notes || '',
    coreMeaning: termRecord.core_meaning || '',
    caseCount: card.caseCount,
    evidenceCount: evidences.length,
    relatedWorks,
    evidenceTypes,
    relatedCases,
    evidences: evidences.slice(0, 12),
    evidencesTruncated: evidences.length > 12,
    raw: {
      id: termRecord.id,
      case_ids: caseIds,
    },
  };
}

function buildCaseDetail(context, caseId) {
  const normalizedId = Number(caseId);
  const caseRecord = context.caseMap.get(normalizedId);
  if (!caseRecord) {
    return null;
  }

  const detail = enrichCase(context, caseRecord);
  const terms = detail.termIds
    .map((termId) => context.termMap.get(termId))
    .filter(Boolean)
    .map((item) => buildTermCard(context, item));
  const evidences = (context.evidenceByCase.get(normalizedId) || []).map((item) => enrichEvidence(context, item));
  const relatedWorks = [...new Set(evidences.map((item) => item.workTitle).filter(Boolean))];
  const evidenceTypes = [...new Set(evidences.map((item) => item.evidenceType).filter(Boolean))];

  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    ...detail,
    terms,
    evidences: evidences.slice(0, 12),
    evidencesTruncated: evidences.length > 12,
    relatedWorks,
    evidenceTypes,
    raw: {
      id: caseRecord.id,
      erwang_passage_id: caseRecord.erwang_passage_id || null,
      target_passage_id: caseRecord.target_passage_id || null,
      term_ids: detail.termIds,
    },
  };
}

function scoreTerm(termRecord, query) {
  const keyword = String(query || '').trim();
  if (!keyword) {
    return 1;
  }

  const aliases = parseJsonArray(termRecord.aliases);
  let score = 0;

  if (termRecord.term === keyword) {
    score += 1000;
  } else if (String(termRecord.term || '').startsWith(keyword)) {
    score += 700;
  } else if (String(termRecord.term || '').includes(keyword)) {
    score += 480;
  }

  if (aliases.includes(keyword)) {
    score += 680;
  } else if (aliases.some((item) => String(item).includes(keyword))) {
    score += 340;
  }

  if (String(termRecord.core_meaning || '').includes(keyword)) {
    score += 220;
  }
  if (String(termRecord.notes || '').includes(keyword)) {
    score += 150;
  }
  if (String(termRecord.category || '').includes(keyword)) {
    score += 90;
  }

  return score;
}

function searchTerms(context, query) {
  const keyword = String(query || '').trim();

  const items = context.terms
    .map((item) => ({
      score: scoreTerm(item, keyword),
      card: buildTermCard(context, item),
    }))
    .filter((item) => item.score > 0)
    .sort((left, right) => {
      if (right.score !== left.score) {
        return right.score - left.score;
      }

      if (right.card.caseCount !== left.card.caseCount) {
        return right.card.caseCount - left.card.caseCount;
      }

      return left.card.id - right.card.id;
    });

  const limit = 6;
  const sliced = items.slice(0, limit).map((item) => item.card);

  return {
    total: items.length,
    limit,
    truncated: items.length > sliced.length,
    items: sliced,
  };
}

function searchCases(context, query) {
  const keyword = normalizeKeyword(query);
  const allItems = context.cases.map((item) => enrichCase(context, item));

  const filteredItems = keyword
    ? allItems.filter((item) => {
        const haystack = [
          item.title,
          item.sectionTitle,
          item.volumeTitle,
          item.termLabel,
          item.termNames.join(' '),
          item.problem,
          item.method,
          item.processText,
          item.conclusion,
          item.certainty,
          item.status,
          item.erwangWorkTitle,
          item.targetWorkTitle,
          item.erwangLocation,
          item.targetLocation,
          item.evidenceQuotes.join(' '),
        ]
          .join(' ')
          .toLowerCase();

        return haystack.includes(keyword);
      })
    : allItems;

  const limit = 6;
  const items = filteredItems.slice(0, limit);

  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    query: String(query || ''),
    total: filteredItems.length,
    limit,
    truncated: filteredItems.length > items.length,
    items,
  };
}

function buildSearch(context, query) {
  const terms = searchTerms(context, query);
  const cases = searchCases(context, query);

  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    query: String(query || ''),
    terms,
    cases,
  };
}

function buildBootstrap(context) {
  const totalRecords = Object.values(context.counts).reduce((sum, value) => sum + value, 0);

  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    schemaVersion: context.snapshot.schemaVersion,
    counts: context.counts,
    totalRecords,
    stores: buildStores(context.counts),
    featuredCases: context.cases.slice(0, 8).map((item) => enrichCase(context, item)),
    sampleTerms: context.terms.slice(0, 12).map((item) => normalizeTerm(item)),
  };
}

function buildSchema(context) {
  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    schemaVersion: context.snapshot.schemaVersion,
    counts: context.counts,
    stores: buildStores(context.counts),
  };
}

function buildTermsPayload(context) {
  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    items: context.terms.map((item) => normalizeTerm(item)),
  };
}

function buildBrowserBootstrap(context) {
  const browserTerms = context.terms.map((item) => buildBrowserTermItem(context, item));
  const browserCases = context.cases.map((item) => buildBrowserCaseItem(context, item));

  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    counts: context.counts,
    views: [
      { value: 'terms', label: '字词浏览', count: browserTerms.length },
      { value: 'cases', label: '案例浏览', count: browserCases.length },
      { value: 'schema', label: '架构说明', count: context.counts.terms + context.counts.cases },
    ],
    termCategories: [
      { value: 'all', label: '全部字词', count: browserTerms.length },
      ...buildCategoryBuckets(browserTerms, (item) => item.category),
    ],
    caseCategories: [
      { value: 'all', label: '全部案例', count: browserCases.length },
      ...buildCategoryBuckets(browserCases, (item) => item.sectionTitle),
    ],
    stores: buildStores(context.counts),
  };
}

function buildBrowserResult(context, options = {}) {
  const view = options.view === 'cases' ? 'cases' : 'terms';
  const category = String(options.category || 'all').trim() || 'all';
  const mode = options.mode === 'fulltext' ? 'fulltext' : 'entry';
  const keyword = normalizeKeyword(options.query);

  if (view === 'cases') {
    const items = context.cases
      .map((item) => buildBrowserCaseItem(context, item))
      .filter((item) => (category === 'all' ? true : (item.sectionTitle || '未分类') === category))
      .filter((item) => {
        if (!keyword) {
          return true;
        }

        const haystack = mode === 'fulltext' ? item.searchFulltext : item.searchEntry;
        return haystack.toLowerCase().includes(keyword);
      })
      .sort((left, right) => right.evidenceCount - left.evidenceCount || left.id - right.id)
      .map(({ searchEntry, searchFulltext, ...item }) => item);

    return {
      ok: true,
      source: context.snapshot.source,
      sourceLabel: context.snapshot.sourceLabel,
      view,
      mode,
      category,
      query: String(options.query || ''),
      total: items.length,
      items,
    };
  }

  const items = context.terms
    .map((item) => ({
      raw: item,
      browserItem: buildBrowserTermItem(context, item),
    }))
    .filter(({ browserItem }) => (category === 'all' ? true : (browserItem.category || '未分类') === category))
    .filter(({ browserItem }) => {
      if (!keyword) {
        return true;
      }

      const haystack = mode === 'fulltext' ? browserItem.searchFulltext : browserItem.searchEntry;
      return haystack.toLowerCase().includes(keyword);
    })
    .sort((left, right) => {
      if (keyword && mode === 'entry') {
        const scoreDiff = scoreTerm(left.raw, keyword) - scoreTerm(right.raw, keyword);
        if (scoreDiff !== 0) {
          return -scoreDiff;
        }
      }

      if (right.browserItem.caseCount !== left.browserItem.caseCount) {
        return right.browserItem.caseCount - left.browserItem.caseCount;
      }

      return left.browserItem.id - right.browserItem.id;
    })
    .map(({ browserItem }) => {
      const { searchEntry, searchFulltext, ...item } = browserItem;
      return item;
    });

  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    view,
    mode,
    category,
    query: String(options.query || ''),
    total: items.length,
    items,
  };
}

function buildTermPayload(context, termId) {
  return buildTermDetail(context, termId);
}

function buildCasePayload(context, caseId) {
  return buildCaseDetail(context, caseId);
}

function buildHealth(context, extra = {}) {
  return {
    ok: true,
    source: context.snapshot.source,
    sourceLabel: context.snapshot.sourceLabel,
    schemaVersion: context.snapshot.schemaVersion,
    counts: context.counts,
    ...extra,
  };
}

module.exports = {
  buildBrowserBootstrap,
  buildBrowserResult,
  buildCasePayload,
  buildSearch,
  buildBootstrap,
  buildContext,
  buildHealth,
  buildSchema,
  buildTermPayload,
  buildTermsPayload,
  parseJsonArray,
  searchCases,
};

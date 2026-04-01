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

function buildTermCard(context, termRecord) {
  const aliases = parseJsonArray(termRecord.aliases);
  const caseIds = parseJsonArray(termRecord.case_ids);
  const relatedCases = caseIds
    .map((caseId) => context.caseMap.get(caseId))
    .filter(Boolean)
    .slice(0, 3)
    .map((item) => buildCaseDisplay(item.title, item.section_title, item.volume_title).displayTitle);

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

  const limit = keyword ? 18 : 12;
  const sliced = items.slice(0, limit).map((item) => item.card);

  return {
    total: items.length,
    limit,
    truncated: items.length > sliced.length,
    items: sliced,
  };
}

function searchCases(context, query) {
  const keyword = String(query || '').trim().toLowerCase();
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

  const limit = keyword ? 60 : 24;
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
  buildSearch,
  buildBootstrap,
  buildContext,
  buildHealth,
  buildSchema,
  buildTermsPayload,
  parseJsonArray,
  searchCases,
};

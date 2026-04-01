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
  buildBootstrap,
  buildContext,
  buildHealth,
  buildSchema,
  buildTermsPayload,
  parseJsonArray,
  searchCases,
};

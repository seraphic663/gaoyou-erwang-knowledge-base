const fs = require('fs');
const OpenCC = require('opencc-js');

const toSimplified = OpenCC.Converter({ from: 'tw', to: 'cn' });
const toTraditional = OpenCC.Converter({ from: 'cn', to: 'tw' });

const snapshotCache = new Map();
const annotationIndexCache = new Map();

function readAnnotationSnapshot(config) {
  const file = config.ANNOTATION_SNAPSHOT_FILE;
  if (!fs.existsSync(file)) {
    throw new Error(`Annotation snapshot not found: ${config.ANNOTATION_SNAPSHOT_FILE}`);
  }

  const stat = fs.statSync(file);
  const cached = snapshotCache.get(file);
  if (cached && cached.mtimeMs === stat.mtimeMs && cached.size === stat.size) {
    return cached.snapshot;
  }

  const snapshot = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
  snapshotCache.set(file, { mtimeMs: stat.mtimeMs, size: stat.size, snapshot });
  annotationIndexCache.delete(file);
  return snapshot;
}

function normalizeKeyword(value) {
  return String(value || '').trim().toLowerCase();
}

function searchVariants(value) {
  const text = normalizeKeyword(value);
  if (!text) return [];
  return [...new Set([
    text,
    normalizeKeyword(toSimplified(text)),
    normalizeKeyword(toTraditional(text)),
  ].filter(Boolean))];
}

function normalizeOrigin(value) {
  const text = String(value || '').trim();
  if (!text) return '未标注出处';
  return text.replace(/^《(.+)》$/, '$1').trim() || '未标注出处';
}

function deriveAnnotator(fileName) {
  const baseName = String(fileName || '')
    .split(/[\\/]/)
    .pop()
    .replace(/\.[^.]+$/, '')
    .trim();
  const segments = baseName.split(/[_-]/).map((segment) => segment.trim()).filter(Boolean);
  return segments.at(-1) || '未标注';
}

function decorateCase(item) {
  const sourceDocument = item.source_document || {};
  return {
    ...item,
    annotator: item.annotator || sourceDocument.annotator || deriveAnnotator(sourceDocument.source_file_name),
    origin: normalizeOrigin(item.origin || item.source_work),
  };
}

function countValues(items, pick) {
  return items.reduce((counts, item) => {
    const value = pick(item);
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
}

function includesText(values, query) {
  if (!query) return true;
  const needles = searchVariants(query);
  return values.some((value) => {
    const haystacks = searchVariants(value);
    return needles.some((needle) => haystacks.some((haystack) => haystack.includes(needle)));
  });
}

function caseSearchValues(item) {
  return [
    item.case_title,
    item.target_work,
    item.target_text,
    item.problem,
    item.claim,
    item.conclusion,
    ...(item.method_tags || []),
    ...(item.terms || []).flatMap((term) => [term.term, term.related_term, term.relation_type, term.note]),
    ...(item.evidences || []).flatMap((evidence) => [evidence.evidence_type, evidence.work, evidence.quote, evidence.role]),
    ...(item.process_steps || []).map((step) => step.text),
  ];
}

function getAnnotationIndex(config) {
  const file = config.ANNOTATION_SNAPSHOT_FILE;
  const snapshot = readAnnotationSnapshot(config);
  const cached = annotationIndexCache.get(file);
  if (cached && cached.snapshot === snapshot) return cached;

  const cases = (snapshot.cases || []).map(decorateCase);
  const indexedCases = cases.map((item) => ({
    item,
    searchValues: caseSearchValues(item),
  }));
  const index = { snapshot, cases, indexedCases };
  annotationIndexCache.set(file, index);
  return index;
}

function buildAnnotationSearchIndex(config) {
  const { snapshot, cases } = getAnnotationIndex(config);
  const annotatorCounts = countValues(cases, (item) => item.annotator);
  const originCounts = countValues(cases, (item) => item.origin);
  const items = cases.map((item) => ({
    id: item.id,
    case_title: item.case_title,
    target_work: item.target_work,
    target_text: item.target_text,
    problem: item.problem,
    claim: item.claim,
    conclusion: item.conclusion,
    certainty: item.certainty,
    method_tags: item.method_tags || [],
    source_document: {
      source_file_name: item.source_document?.source_file_name || '',
      doc_type: item.source_document?.doc_type || '',
    },
    annotator: item.annotator,
    origin: item.origin,
    search_text: caseSearchValues(item)
      .flatMap((value) => searchVariants(value))
      .join('\u0001'),
  }));

  return {
    ok: true,
    source: snapshot.source,
    sourceLabel: snapshot.sourceLabel,
    schemaVersion: snapshot.schemaVersion,
    description: snapshot.description,
    counts: snapshot.counts || {},
    documents: buildBuckets(snapshot.documentCounts || {}, '全部文档', snapshot.counts?.cases || 0),
    methods: buildBuckets(snapshot.methodCounts || {}, '全部方法', snapshot.counts?.cases || 0),
    annotators: buildBuckets(annotatorCounts, '全部标注者', snapshot.counts?.cases || cases.length),
    origins: buildBuckets(originCounts, '全部出处', snapshot.counts?.cases || cases.length),
    items,
  };
}

function getAnnotationCase(config, id) {
  const targetId = String(id || '').trim();
  if (!targetId) return null;
  const { cases } = getAnnotationIndex(config);
  return cases.find((item) => String(item.id) === targetId) || null;
}

function normalizeFilterValues(value) {
  const values = Array.isArray(value) ? value : [value];
  return [...new Set(values
    .flatMap((item) => String(item || '').split('|'))
    .map((item) => item.trim())
    .filter((item) => item && item !== 'all'))];
}

function compareCaseIds(left, right) {
  const leftId = Number(left.id);
  const rightId = Number(right.id);
  if (Number.isFinite(leftId) && Number.isFinite(rightId)) return leftId - rightId;
  return String(left.id || '').localeCompare(String(right.id || ''), 'zh-CN', { numeric: true });
}

function buildBuckets(counts, allLabel, allCount = null) {
  return [
    {
      value: 'all',
      label: allLabel,
      count: allCount ?? Object.values(counts || {}).reduce((sum, count) => sum + Number(count || 0), 0),
    },
    ...Object.keys(counts || {}).sort().map((name) => ({
      value: name,
      label: name,
      count: counts[name],
    })),
  ];
}

function buildAnnotationBootstrap(config) {
  const { snapshot, cases } = getAnnotationIndex(config);
  const annotatorCounts = countValues(cases, (item) => item.annotator);
  const originCounts = countValues(cases, (item) => item.origin);

  return {
    ok: true,
    source: snapshot.source,
    sourceLabel: snapshot.sourceLabel,
    schemaVersion: snapshot.schemaVersion,
    description: snapshot.description,
    counts: snapshot.counts || {},
    documents: buildBuckets(snapshot.documentCounts || {}, '全部文档', snapshot.counts?.cases || 0),
    methods: buildBuckets(snapshot.methodCounts || {}, '全部方法', snapshot.counts?.cases || 0),
    annotators: buildBuckets(annotatorCounts, '全部标注者', snapshot.counts?.cases || cases.length),
    origins: buildBuckets(originCounts, '全部出处', snapshot.counts?.cases || cases.length),
  };
}

function browseAnnotations(config, options = {}) {
  const { snapshot, indexedCases } = getAnnotationIndex(config);
  const query = String(options.query || '');
  const document = String(options.document || 'all').trim() || 'all';
  const method = String(options.method || 'all').trim() || 'all';
  const annotators = normalizeFilterValues(options.annotators ?? options.annotator);
  const origins = normalizeFilterValues(options.origins ?? options.origin).map(normalizeOrigin);
  const requestedPage = Number.parseInt(options.page, 10);
  const requestedPageSize = Number.parseInt(options.pageSize, 10);
  const pageSize = Number.isFinite(requestedPageSize) && requestedPageSize > 0 ? Math.min(requestedPageSize, 100) : 50;
  const page = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const allItems = indexedCases
    .filter(({ item, searchValues }) => {
      const docName = item.source_document?.source_file_name || '未标注文档';
      const methodOk = method === 'all' || (item.method_tags || []).includes(method);
      const documentOk = document === 'all' || docName === document;
      const annotatorOk = !annotators.length || annotators.includes(item.annotator);
      const originOk = !origins.length || origins.includes(item.origin);
      return methodOk && documentOk && annotatorOk && originOk && includesText(searchValues, query);
    })
    .map(({ item }) => item)
    .sort(compareCaseIds);

  const total = allItems.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(page, totalPages);
  const start = (currentPage - 1) * pageSize;

  return {
    ok: true,
    source: snapshot.source,
    sourceLabel: snapshot.sourceLabel,
    query,
    document,
    method,
    annotator: annotators.length === 1 ? annotators[0] : 'all',
    annotators,
    origin: origins.length === 1 ? origins[0] : 'all',
    origins,
    total,
    page: currentPage,
    pageSize,
    totalPages,
    items: allItems.slice(start, start + pageSize),
    counts: snapshot.counts || {},
  };
}

module.exports = {
  buildAnnotationSearchIndex,
  browseAnnotations,
  buildAnnotationBootstrap,
  deriveAnnotator,
  getAnnotationCase,
  normalizeOrigin,
  searchVariants,
};

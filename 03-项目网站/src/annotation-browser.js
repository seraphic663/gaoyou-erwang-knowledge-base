const fs = require('fs');

function readAnnotationSnapshot(config) {
  if (!fs.existsSync(config.ANNOTATION_SNAPSHOT_FILE)) {
    throw new Error(`Annotation snapshot not found: ${config.ANNOTATION_SNAPSHOT_FILE}`);
  }

  return JSON.parse(fs.readFileSync(config.ANNOTATION_SNAPSHOT_FILE, 'utf8').replace(/^\uFEFF/, ''));
}

function normalizeKeyword(value) {
  return String(value || '').trim().toLowerCase();
}

function includesText(values, query) {
  if (!query) return true;
  const needle = normalizeKeyword(query);
  return values.some((value) => String(value || '').toLowerCase().includes(needle));
}

function caseSearchValues(item) {
  return [
    item.case_title,
    item.source_work,
    item.target_work,
    item.target_text,
    item.problem,
    item.claim,
    item.conclusion,
    item.certainty,
    item.status,
    ...(item.method_tags || []),
    ...(item.terms || []).flatMap((term) => [term.term, term.related_term, term.relation_type, term.note]),
    ...(item.evidences || []).flatMap((evidence) => [evidence.evidence_type, evidence.work, evidence.quote, evidence.role]),
    ...(item.process_steps || []).flatMap((step) => [step.step_type, step.text]),
  ];
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
  const snapshot = readAnnotationSnapshot(config);

  return {
    ok: true,
    source: snapshot.source,
    sourceLabel: snapshot.sourceLabel,
    schemaVersion: snapshot.schemaVersion,
    description: snapshot.description,
    counts: snapshot.counts || {},
    documents: buildBuckets(snapshot.documentCounts || {}, '全部文档', snapshot.counts?.cases || 0),
    methods: buildBuckets(snapshot.methodCounts || {}, '全部方法', snapshot.counts?.cases || 0),
  };
}

function browseAnnotations(config, options = {}) {
  const snapshot = readAnnotationSnapshot(config);
  const query = String(options.query || '');
  const document = String(options.document || 'all').trim() || 'all';
  const method = String(options.method || 'all').trim() || 'all';
  const requestedPage = Number.parseInt(options.page, 10);
  const requestedPageSize = Number.parseInt(options.pageSize, 10);
  const pageSize = Number.isFinite(requestedPageSize) && requestedPageSize > 0 ? Math.min(requestedPageSize, 100) : 50;
  const page = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const allItems = (snapshot.cases || [])
    .filter((item) => {
      const docName = item.source_document?.source_file_name || '未标注文档';
      const methodOk = method === 'all' || (item.method_tags || []).includes(method);
      const documentOk = document === 'all' || docName === document;
      return methodOk && documentOk && includesText(caseSearchValues(item), query);
    });

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
    total,
    page: currentPage,
    pageSize,
    totalPages,
    items: allItems.slice(start, start + pageSize),
    counts: snapshot.counts || {},
  };
}

module.exports = {
  browseAnnotations,
  buildAnnotationBootstrap,
};

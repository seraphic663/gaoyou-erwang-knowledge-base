const { resolvePage, renderNavigation } = require('./site-routes');
const { getAuditTargets } = require('./site-identity');
const fs = require('fs');
const http = require('http');
const path = require('path');
const config = require('./config');
const readingHarness = require('./reading-harness');
const {
  browseAnnotations,
  buildAnnotationBootstrap,
  buildAnnotationSearchIndex,
  getAnnotationCase,
} = require('./annotation-browser');
const { createDataSource } = require('./data-source');
const { getV2Acceptance } = require('./v2-acceptance');
const { retrieveForCase, retrieveFromCorpus } = require('./corpus-retrieval');
const { runPythonJsonBridge } = require('./python-bridge');
const { getV2ReviewTasks, getV2ReviewTask, submitV2Review } = require('./v2-review');
const {
  ACCEPTED_PROMPT_VERSIONS,
  ALLOWED_EFFORTS,
  ALLOWED_MODELS,
  PROMPT_VERSION,
  generateFiveStepDraft,
  fingerprintV2Case,
  STEPS,
  validateReviewedSteps,
} = require('./v2-five-step-audit');
const {
  deleteV2FiveStepAudit,
  getV2FiveStepAudit,
  getV2FiveStepAudits,
  restoreV2FiveStepAudit,
  reviseV2FiveStepAudit,
  saveV2FiveStepAudit,
} = require('./v2-five-step-audit-store');

let v2SummaryCache = null;

async function retrieveOriginalForUnifiedSearch(config, {
  query,
  workKey = '',
  limit = 8,
  searchMode = 'unified',
} = {}) {
  const args = ['--query', query, '--limit', String(limit), '--search-mode', searchMode];
  if (workKey) args.push('--work-key', workKey);
  args.push('--include-cases');
  return runPythonJsonBridge(config, {
    bridgeFile: config.CORPUS_RETRIEVAL_BRIDGE_FILE,
    command: 'retrieve',
    args,
    dbFile: config.CORPUS_DB_FILE,
    errorLabel: 'unified original corpus retrieval',
  });
}

function fileRevision(filePath) {
  try {
    const stat = fs.statSync(filePath);
    return `${filePath}:${stat.mtimeMs}:${stat.size}`;
  } catch {
    return `${filePath}:missing`;
  }
}

function v2SummaryCacheKey(config) {
  const v2DataDir = path.dirname(config.V2_DB_FILE);
  return [
    config.V2_DB_FILE,
    path.join(v2DataDir, 'v2_validation_report.json'),
    path.join(v2DataDir, 'review_tasks', 'review_task_manifest.review.v1.json'),
    path.join(v2DataDir, 'work_queues_report.json'),
  ].map(fileRevision).join('|');
}

function sendJson(res, statusCode, payload, extraHeaders = {}) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, no-cache, must-revalidate',
    'Pragma': 'no-cache',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    ...extraHeaders,
  });
  res.end(JSON.stringify(payload, null, 2));
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let bytes = 0;
    let tooLarge = false;

    req.on('data', (chunk) => {
      bytes += chunk.length;
      if (bytes > 128000) tooLarge = true;
      else if (!tooLarge) chunks.push(chunk);
    });

    req.on('end', () => {
      if (tooLarge) {
        reject(new Error('Request body too large'));
        return;
      }
      const body = Buffer.concat(chunks).toString('utf8');
      if (!body.trim()) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(body));
      } catch {
        reject(new Error('Invalid JSON body'));
      }
    });

    req.on('error', reject);
  });
}

function sendFile(res, filePath, transform = null) {
  const extension = path.extname(filePath).toLowerCase();
  const contentTypes = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
  };

  try {
    const stat = fs.statSync(filePath);
    if (!stat.isFile()) {
      throw new Error('Not a file');
    }

    res.writeHead(200, {
      'Content-Type': contentTypes[extension] || 'application/octet-stream',
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Pragma': 'no-cache',
    });
    const content = fs.readFileSync(filePath);
    res.end(transform ? transform(content.toString('utf8')) : content);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Not Found');
  }
}

function safeResolve(baseDir, requestPath) {
  const decoded = decodeURIComponent(requestPath || '/');
  const cleaned = decoded.replace(/^\/+/, '');
  const absolutePath = path.resolve(baseDir, cleaned);
  const normalizedBase = path.resolve(baseDir);

  if (!absolutePath.startsWith(normalizedBase)) {
    return null;
  }

  return absolutePath;
}

function resolveStaticFile(requestPath) {
  if (requestPath === '/') {
    return path.join(config.WEB_DIR, 'index.html');
  }

  if (requestPath.startsWith('/media/')) {
    const mediaPath = safeResolve(config.MEDIA_DIR, requestPath.slice('/media/'.length));
    return mediaPath || path.join(config.WEB_DIR, '404.not-found');
  }

  const relativePath = requestPath;
  const staticPath = safeResolve(config.WEB_DIR, relativePath);
  return staticPath || path.join(config.WEB_DIR, '404.not-found');
}

async function getCachedV2Summary(config) {
  const cacheKey = v2SummaryCacheKey(config);
  if (
    v2SummaryCache
    && v2SummaryCache.cacheKey === cacheKey
    && v2SummaryCache.payload
  ) {
    return v2SummaryCache.payload;
  }

  if (v2SummaryCache?.cacheKey === cacheKey && v2SummaryCache.pending) {
    return v2SummaryCache.pending;
  }

  const pending = getV2Acceptance(config, 'summary');
  v2SummaryCache = {
    cacheKey,
    expiresAt: 0,
    pending,
  };
  try {
    const payload = await pending;
    v2SummaryCache = {
      cacheKey,
      payload,
    };
    return payload;
  } catch (error) {
    if (v2SummaryCache?.pending === pending) {
      v2SummaryCache = null;
    }
    throw error;
  }
}

function createServer() {
  const dataSource = createDataSource(config);

  async function handleApi(req, res, parsedUrl) {
    try {
      if (req.method === 'OPTIONS') {
        return sendJson(res, 204, {});
      }

      if (parsedUrl.pathname.startsWith('/api/reading-harness/')) {
        const command = parsedUrl.pathname.slice('/api/reading-harness/'.length);
        if (['summary', 'sources', 'chunks', 'chunk'].includes(command)) {
          if (req.method !== 'GET') return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
          const checked = readingHarness.validateBrowseInput(command, parsedUrl.query);
          if (checked.error) return sendJson(res, 400, { ok: false, message: checked.error });
          try {
            const data = await readingHarness.runCorpusBridge(config, command, checked.input);
            return sendJson(res, 200, { ok: true, data });
          } catch (error) {
            return sendJson(res, 502, { ok: false, message: `external_corpus_failed: ${error.message}` });
          }
        }
        if (['retrieve', 'generate'].includes(command)) {
          if (req.method !== 'POST') return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
          let body;
          try { body = await readJsonBody(req); }
          catch (error) { return sendJson(res, 400, { ok: false, message: error.message }); }
          const outcome = command === 'retrieve'
            ? await readingHarness.retrieve(config, body)
            : await readingHarness.generate(config, body);
          return sendJson(res, outcome.status, outcome.payload);
        }
        return sendJson(res, 404, { ok: false, message: 'API not found' });
      }

      if (parsedUrl.pathname === '/api/site/audit-targets') {
        if (req.method !== 'GET') return sendJson(res, 405, {ok:false});
        const source = parsedUrl.query.source;
        if (!['main', 'annotation', 'v2'].includes(source)) return sendJson(res, 400, {ok:false,message:'invalid_source'});
        const ids = parsedUrl.queryValues.id || [];
        if (!ids.length || ids.length > 100) return sendJson(res, 400, {ok:false,message:'provide_1_to_100_ids'});
        return sendJson(res, 200, await getAuditTargets(config, source, ids));
      }
      if (parsedUrl.pathname === '/api/health') {
        return sendJson(res, 200, dataSource.getHealth());
      }

      if (parsedUrl.pathname === '/api/bootstrap') {
        return sendJson(res, 200, dataSource.getBootstrap());
      }

      if (parsedUrl.pathname === '/api/schema') {
        return sendJson(res, 200, dataSource.getSchema());
      }

      if (parsedUrl.pathname === '/api/browser/bootstrap') {
        return sendJson(res, 200, dataSource.getBrowserBootstrap());
      }

      if (parsedUrl.pathname === '/api/browser') {
        return sendJson(res, 200, dataSource.browse({
          view: parsedUrl.query.view,
          category: parsedUrl.query.category,
          mode: parsedUrl.query.mode,
          query: parsedUrl.query.q || '',
          page: parsedUrl.query.page,
          pageSize: parsedUrl.query.pageSize,
        }));
      }

      if (parsedUrl.pathname === '/api/annotation/bootstrap') {
        return sendJson(res, 200, buildAnnotationBootstrap(config));
      }

      if (parsedUrl.pathname === '/api/annotation/index') {
        const startedAt = process.hrtime.bigint();
        const payload = buildAnnotationSearchIndex(config);
        const apiTimeMs = Number(process.hrtime.bigint() - startedAt) / 1e6;
        return sendJson(res, 200, payload, {
          'X-API-Time-Ms': apiTimeMs.toFixed(3),
          'Server-Timing': 'annotation-index;dur=' + apiTimeMs.toFixed(3),
        });
      }

      if (parsedUrl.pathname === '/api/annotation/detail') {
        const startedAt = process.hrtime.bigint();
        const item = getAnnotationCase(config, parsedUrl.query.id);
        const apiTimeMs = Number(process.hrtime.bigint() - startedAt) / 1e6;
        if (!item) {
          return sendJson(res, 404, { ok: false, message: 'annotation_case_not_found' }, {
            'X-API-Time-Ms': apiTimeMs.toFixed(3),
            'Server-Timing': 'annotation-detail;dur=' + apiTimeMs.toFixed(3),
          });
        }
        return sendJson(res, 200, { ok: true, item }, {
          'X-API-Time-Ms': apiTimeMs.toFixed(3),
          'Server-Timing': 'annotation-detail;dur=' + apiTimeMs.toFixed(3),
        });
      }

      if (parsedUrl.pathname === '/api/annotation') {
        const startedAt = process.hrtime.bigint();
        const payload = browseAnnotations(config, {
          query: parsedUrl.query.q || '',
          document: parsedUrl.query.document,
          method: parsedUrl.query.method,
          annotators: parsedUrl.queryValues.annotator,
          origins: parsedUrl.queryValues.origin,
          page: parsedUrl.query.page,
          pageSize: parsedUrl.query.pageSize,
        });
        const apiTimeMs = Number(process.hrtime.bigint() - startedAt) / 1e6;
        return sendJson(res, 200, payload, {
          'X-API-Time-Ms': apiTimeMs.toFixed(3),
          'Server-Timing': 'annotation-search;dur=' + apiTimeMs.toFixed(3),
        });
      }

      if (parsedUrl.pathname === '/api/v2/summary') {
        if (req.method !== 'GET') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        return sendJson(res, 200, await getCachedV2Summary(config));
      }

      if (parsedUrl.pathname === '/api/corpus/unified-search') {
        if (req.method !== 'POST') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        let body;
        try { body = await readJsonBody(req); }
        catch (error) { return sendJson(res, 400, { ok: false, message: error.message }); }
        const query = typeof body.query === 'string' ? body.query.trim() : '';
        if (!query) return sendJson(res, 400, { ok: false, message: 'query_required' });
        if (Array.from(query).length > 1000) {
          return sendJson(res, 400, { ok: false, message: 'query_exceeds_1000_characters' });
        }
        const allowedCollections = new Set([
          'original', 'external_high', 'external_mid', 'external_low',
        ]);
        let collections = body.collections;
        if (collections === undefined) collections = ['original', 'external_high', 'external_mid', 'external_low'];
        if (!Array.isArray(collections) || collections.some((value) => typeof value !== 'string')) {
          return sendJson(res, 400, { ok: false, message: 'collections_must_be_string_array' });
        }
        collections = [...new Set(collections)];
        if (collections.some((value) => !allowedCollections.has(value))) {
          return sendJson(res, 400, { ok: false, message: 'invalid_collection' });
        }
        if (!collections.length) return sendJson(res, 400, { ok: false, message: 'no_collection_selected' });
        const mode = String(body.mode || 'unified');
        if (!['unified', 'body', 'title'].includes(mode)) {
          return sendJson(res, 400, { ok: false, message: 'invalid_search_mode' });
        }
        const requestedLimit = Number(body.limit ?? 8);
        const titleOffset = Number(body.title_offset ?? 0);
        if (!Number.isInteger(requestedLimit) || requestedLimit < 1 || requestedLimit > 20
          || !Number.isInteger(titleOffset) || titleOffset < 0 || titleOffset > 100000) {
          return sendJson(res, 400, { ok: false, message: 'invalid_pagination' });
        }
        const workKey = typeof body.work_key === 'string' ? body.work_key.slice(0, 100) : '';
        const includeOriginal = collections.includes('original');
        const externalCollections = collections.filter((value) => value.startsWith('external_'));
        const includeBody = mode !== 'title';
        const includeTitle = mode !== 'body';
        const workLabels = {
          dushu_zazhi: '《读书杂志》',
          guangya_shuzheng: '《广雅疏证》',
          jingyi_shuwen: '《经义述闻》',
          jingzhuan_shici: '《经传释词》',
        };
        const collectionLabels = {
          external_high: '外典·高频',
          external_mid: '外典·中频',
          external_low: '外典·低频',
        };
        const tasks = [];
        if (includeOriginal) {
          tasks.push((async () => {
            const data = await retrieveOriginalForUnifiedSearch(config, {
              query,
              workKey,
              limit: Math.min(requestedLimit, 20),
              searchMode: mode,
            });
            const items = (data.items || []).map((item) => {
              const reason = String(item.match_reason || '');
              const titleHit = reason.includes('篇目标题命中');
              const bodyHit = /完整短语命中|简繁字形转换后命中|正文片段命中/.test(reason);
              const matchScope = titleHit && bodyHit ? 'both' : titleHit ? 'title' : 'body';
              return {
                ...item,
                kind: 'original_passage',
                collection: 'original',
                collection_label: '二王原典',
                match_scope: matchScope,
                match_label: matchScope === 'both' ? '书名与正文命中'
                  : matchScope === 'title' ? '书名命中' : '正文命中',
                source_title: item.document_title || workLabels[item.work_key] || item.work_key || '原典',
                matched_text: item.passage_text || '',
                result_id: item.passage_id,
                location: [item.document_title, item.section_title, item.entry_title]
                  .filter(Boolean).join(' · ') || workLabels[item.work_key] || item.work_key || '篇目未注明',
              };
            });
            return {
              kind: 'original',
              items,
              candidate_count: data.candidate_count || 0,
              candidate_count_capped: Boolean(data.candidate_count_capped),
              returned_count: data.returned_count || (data.items || []).length,
            };
          })());
        }
        if (externalCollections.length && includeBody) {
          tasks.push((async () => {
            const outcome = await readingHarness.retrieve(config, {
              original_text: query,
              question: query,
              collections: externalCollections,
            });
            if (outcome.status !== 200 || !outcome.payload?.ok) {
              throw new Error(outcome.payload?.message || 'external_retrieval_failed');
            }
            const data = outcome.payload.data || {};
            const items = (data.items || []).map((item) => ({
              ...item,
              kind: 'external_chunk',
              match_scope: 'body',
              match_label: '正文命中',
              collection_label: collectionLabels[item.collection] || item.collection,
              source_title: item.source_title || '外典书名未注明',
              matched_text: item.full_text || item.context_text || '',
              result_id: item.chunk_id,
              location: [item.source_title, item.chapter, `第${item.ordinal}段`]
                .filter(Boolean).join(' · '),
            }));
            return {
              kind: 'external_body',
              items,
              candidate_count: data.candidate_count || 0,
              returned_count: data.hit_count || items.length,
              collections: data.collections || externalCollections,
              reason: data.reason || '',
            };
          })());
        }
        if (externalCollections.length && includeTitle) {
          tasks.push((async () => {
            const data = await readingHarness.runCorpusBridge(config, 'sources', {
              query,
              collections: externalCollections,
              limit: Math.min(requestedLimit, 100),
              offset: titleOffset,
            });
            const items = (data.items || []).map((item) => {
              const titleHit = String(item.title || '').normalize('NFKC').includes(query.normalize('NFKC'));
              const relpathHit = String(item.relpath || '').normalize('NFKC').includes(query.normalize('NFKC'));
              return {
                ...item,
                kind: 'external_source',
                match_scope: titleHit ? 'title' : 'path',
                match_label: titleHit ? '书名命中' : relpathHit ? '路径命中' : '来源信息命中',
                collection_label: collectionLabels[item.collection] || item.collection,
                source_title: item.title || '外典书名未注明',
                matched_text: titleHit ? item.title : item.relpath,
                result_id: `source:${item.source_id}`,
                location: item.relpath || '',
              };
            });
            return {
              kind: 'external_title',
              items,
              total: data.total || 0,
              returned_count: items.length,
              offset: data.offset || 0,
              limit: data.limit || requestedLimit,
            };
          })());
        }
        try {
          const parts = await Promise.all(tasks);
          const byKind = Object.fromEntries(parts.map((part) => [part.kind, part]));
          const items = parts.flatMap((part) => part.items || []);
          return sendJson(res, 200, {
            ok: true,
            query,
            mode,
            collections,
            items,
            counts: {
              original: {
                candidate_count: byKind.original?.candidate_count || 0,
                candidate_count_capped: Boolean(byKind.original?.candidate_count_capped),
                returned_count: byKind.original?.returned_count || 0,
              },
              external_body: {
                candidate_count: byKind.external_body?.candidate_count || 0,
                returned_count: byKind.external_body?.returned_count || 0,
                result_limit: byKind.external_body ? 6 : 0,
              },
              external_title: {
                total: byKind.external_title?.total || 0,
                returned_count: byKind.external_title?.returned_count || 0,
                offset: byKind.external_title?.offset || 0,
                limit: byKind.external_title?.limit || requestedLimit,
              },
            },
          });
        } catch (error) {
          return sendJson(res, 502, { ok: false, message: `corpus_search_failed: ${error.message}` });
        }
      }

      if (parsedUrl.pathname === '/api/corpus/retrieve') {
        if (req.method !== 'GET') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        const caseId = parsedUrl.query.case_id || '';
        const query = parsedUrl.query.q || '';
        const workKey = parsedUrl.query.work_key || '';
        const limit = Number(parsedUrl.query.limit || 8);
        const includeCases = ['1', 'true', 'yes'].includes(String(parsedUrl.query.include_cases || '').toLowerCase());
        if (caseId) {
          const casePayload = await getV2Acceptance(config, 'case', [caseId]);
          if (!casePayload?.ok) return sendJson(res, 404, casePayload);
          const retrieval = await retrieveForCase(config, casePayload, { limit });
          return sendJson(res, 200, {
            ...retrieval,
            case_id: caseId,
            case_title: casePayload.case_title,
          });
        }
        if (!query.trim()) {
          return sendJson(res, 400, { ok: false, message: 'query_required' });
        }
        return sendJson(res, 200, await retrieveFromCorpus(config, {
          query,
          workKey,
          limit,
          includeCases,
        }));
      }

      if (parsedUrl.pathname === '/api/v2/cases') {
        if (req.method !== 'GET') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        const bridgeArgs = [];
        const query = parsedUrl.query.q || '';
        const sourceWork = parsedUrl.query.source_work || '';
        const machineStatus = parsedUrl.query.machine_status || '';
        const page = parsedUrl.query.page || '';
        const pageSize = parsedUrl.query.pageSize || '';
        if (query) bridgeArgs.push('--query', query);
        if (sourceWork) bridgeArgs.push('--source-work', sourceWork);
        if (machineStatus) bridgeArgs.push('--machine-status', machineStatus);
        if (page) bridgeArgs.push('--page', page);
        if (pageSize) bridgeArgs.push('--page-size', pageSize);
        return sendJson(res, 200, await getV2Acceptance(config, 'cases', bridgeArgs));
      }

      if (parsedUrl.pathname === '/api/v2/case') {
        if (req.method !== 'GET') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        const caseId = parsedUrl.query.id || '';
        const payload = await getV2Acceptance(config, 'case', [caseId]);
        if (!payload.ok) {
          return sendJson(res, 404, payload);
        }
        return sendJson(res, 200, payload);
      }

      if (parsedUrl.pathname === '/api/v2/five-step-draft') {
        if (req.method !== 'POST') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        const body = await readJsonBody(req);
        const result = await generateFiveStepDraft(config, body);
        return sendJson(res, result.status, result.payload);
      }

      if (parsedUrl.pathname === '/api/v2/five-step-audits') {
        if (req.method === 'GET') {
          const caseId = parsedUrl.query.case_id || '';
          const payload = await getV2FiveStepAudits(config, caseId);
          payload.write_enabled = config.V2_FIVE_STEP_AUDIT_WRITE_ENABLED;
          return sendJson(res, payload.ok === false ? 404 : 200, payload);
        }
        if (!['POST', 'PATCH', 'DELETE'].includes(req.method)) {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        if (!config.V2_FIVE_STEP_AUDIT_WRITE_ENABLED) {
          return sendJson(res, 403, {
            ok: false,
            write_enabled: false,
            message: '当前服务处于只读状态，暂时不能保存本次审校。',
          });
        }

        const body = await readJsonBody(req);

        if (req.method === 'DELETE') {
          const auditId = String(body.audit_id || '').trim();
          const deletedBy = String(body.deleted_by || '').trim();
          const operationId = String(body.operation_id || '').trim();
          if (!auditId || !deletedBy || !operationId) {
            return sendJson(res, 400, { ok: false, message: 'audit_id_deleted_by_operation_id_required' });
          }
          const payload = await deleteV2FiveStepAudit(config, {
            audit_id: auditId,
            deleted_by: deletedBy,
            operation_id: operationId,
            delete_reason: String(body.delete_reason || ''),
          });
          return sendJson(res, payload.ok === false ? 400 : 200, payload);
        }

        if (req.method === 'PATCH') {
          const auditId = String(body.audit_id || '').trim();
          const caseId = String(body.case_id || '').trim();
          const reviewer = String(body.reviewer || '').trim();
          const operationId = String(body.operation_id || '').trim();
          if (!auditId || !caseId || !reviewer || !operationId) {
            return sendJson(res, 400, { ok: false, message: 'audit_id_case_id_reviewer_operation_id_required' });
          }
          let reviewedSteps;
          try {
            reviewedSteps = validateReviewedSteps(body.reviewed_steps);
          } catch (error) {
            return sendJson(res, 400, { ok: false, message: error.message });
          }
          if (!['reviewed', 'needs_revision', 'uncertain'].includes(body.overall_decision)) {
            return sendJson(res, 400, { ok: false, message: 'overall_decision_invalid' });
          }
          const currentCase = await getV2Acceptance(config, 'case', [caseId]);
          if (!currentCase?.ok) return sendJson(res, 404, { ok: false, message: 'V2 case not found.' });
          const sourcePayload = await getV2FiveStepAudit(config, auditId);
          if (!sourcePayload?.ok || !sourcePayload.record) {
            return sendJson(res, 404, { ok: false, message: 'Five-step audit record not found.' });
          }
          const source = sourcePayload.record;
          if (source.case_id !== caseId) return sendJson(res, 409, { ok: false, message: 'audit_record_case_mismatch' });
          if (source.case_fingerprint !== fingerprintV2Case(currentCase)) {
            return sendJson(res, 409, { ok: false, message: 'V2 case changed after this record was created. Regenerate before editing.' });
          }
          const payload = await reviseV2FiveStepAudit(config, {
            source_audit_id: auditId,
            case_id: caseId,
            reviewer,
            operation_id: operationId,
            case_fingerprint: source.case_fingerprint,
            reviewed_steps: reviewedSteps,
            overall_decision: body.overall_decision,
            overall_note: String(body.overall_note || ''),
          });
          return sendJson(res, payload.ok === false ? 400 : 200, payload);
        }

        if (body.mode === 'restore') {
          const auditId = String(body.audit_id || '').trim();
          const restoredBy = String(body.restored_by || '').trim();
          const operationId = String(body.operation_id || '').trim();
          if (!auditId || !restoredBy || !operationId) {
            return sendJson(res, 400, { ok: false, message: 'audit_id_restored_by_operation_id_required' });
          }
          const payload = await restoreV2FiveStepAudit(config, {
            audit_id: auditId,
            restored_by: restoredBy,
            operation_id: operationId,
          });
          return sendJson(res, payload.ok === false ? 400 : 200, payload);
        }

        const caseId = String(body.case_id || '').trim();
        const reviewer = String(body.reviewer || '').trim();
        const operationId = String(body.operation_id || '').trim();
        if (!caseId || !reviewer || !operationId) {
          return sendJson(res, 400, { ok: false, message: 'case_id_reviewer_operation_id_required' });
        }
        if (!ALLOWED_MODELS.has(body.model_requested)
          || !ALLOWED_EFFORTS.has(body.reasoning_effort)
          || !ACCEPTED_PROMPT_VERSIONS.has(String(body.prompt_version || ''))
          || !String(body.model_returned || '').trim()
          || !String(body.generated_at || '').trim()) {
          return sendJson(res, 400, { ok: false, message: 'model_effort_prompt_version_and_generation_time_required' });
        }
        const currentCase = await getV2Acceptance(config, 'case', [caseId]);
        if (!currentCase?.ok) return sendJson(res, 404, { ok: false, message: 'V2 case not found.' });
        if (body.case_fingerprint !== fingerprintV2Case(currentCase)) {
          return sendJson(res, 409, { ok: false, message: 'V2 case changed after draft generation. Reload the case and regenerate before saving.' });
        }

        const aiDraft = body.ai_draft;
        const reviewedSteps = body.reviewed_steps;
        if (!Array.isArray(aiDraft) || !Array.isArray(reviewedSteps)
          || aiDraft.length !== STEPS.length || reviewedSteps.length !== STEPS.length
          || STEPS.some(({ field }, index) => aiDraft[index]?.field !== field || reviewedSteps[index]?.field !== field)) {
          return sendJson(res, 400, { ok: false, message: 'exactly_five_ordered_steps_required' });
        }
        if (aiDraft.some((step) => !String(step.text || '').trim()
          || !Array.isArray(step.evidence_refs) || !Array.isArray(step.review_questions))) {
          return sendJson(res, 400, { ok: false, message: 'ai_draft_step_schema_invalid' });
        }
        const availableEvidenceIndexes = new Set((currentCase.evidences || []).map((entry) => Number(entry.evidence_index)));
        if (aiDraft.some((step) => step.evidence_refs.some((index) => !availableEvidenceIndexes.has(Number(index))))) {
          return sendJson(res, 400, { ok: false, message: 'ai_draft_references_unknown_v2_evidence' });
        }
        const reviewStatuses = new Set(['accepted', 'edited', 'question']);
        if (reviewedSteps.some((step) => !reviewStatuses.has(step.status) || !String(step.text || '').trim()
          || (['edited', 'question'].includes(step.status) && !String(step.comment || '').trim()))) {
          return sendJson(res, 400, { ok: false, message: 'each_step_requires_text_and_review_decision' });
        }
        if (!['reviewed', 'needs_revision', 'uncertain'].includes(body.overall_decision)) {
          return sendJson(res, 400, { ok: false, message: 'overall_decision_invalid' });
        }

        const payload = await saveV2FiveStepAudit(config, {
          case_id: caseId,
          reviewer,
          operation_id: operationId,
          model_requested: body.model_requested,
          model_returned: body.model_returned,
          reasoning_effort: body.reasoning_effort,
          prompt_version: body.prompt_version,
          case_fingerprint: body.case_fingerprint,
          generated_at: body.generated_at,
          audit_json: {
            overall_decision: body.overall_decision,
            overall_note: String(body.overall_note || ''),
            output_budget_tokens: body.output_budget_tokens || null,
            review_view_mode: ['simple', 'detailed'].includes(body.review_view_mode) ? body.review_view_mode : 'simple',
            usage: body.usage || null,
            retrieval_materials: body.retrieval_materials || null,
            ai_draft: aiDraft,
            reviewed_steps: reviewedSteps,
          },
        });
        return sendJson(res, payload.ok === false ? 400 : 200, payload);
      }

      if (parsedUrl.pathname === '/api/v2/review-tasks') {
        if (req.method !== 'GET') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        const payload = await getV2ReviewTasks(config, {
          stream: parsedUrl.query.stream || 'case_review',
          batch: parsedUrl.query.batch ? Number(parsedUrl.query.batch) : undefined,
        });
        payload.write_enabled = config.V2_REVIEW_WRITE_ENABLED;
        return sendJson(res, payload.ok === false ? 400 : 200, payload);
      }

      if (parsedUrl.pathname === '/api/v2/review-task') {
        if (req.method !== 'GET') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        const payload = await getV2ReviewTask(config, parsedUrl.query.id || '');
        payload.write_enabled = config.V2_REVIEW_WRITE_ENABLED;
        return sendJson(res, payload.ok === false ? 404 : 200, payload);
      }

      if (parsedUrl.pathname === '/api/v2/review') {
        if (req.method !== 'POST') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        if (!config.V2_REVIEW_WRITE_ENABLED) {
          return sendJson(res, 403, {
            ok: false,
            write_enabled: false,
            message: 'V2 review writes are disabled; set V2_REVIEW_WRITE_ENABLED=1 for an explicit local review session',
          });
        }
        const body = await readJsonBody(req);
        const payload = await submitV2Review(config, body);
        return sendJson(res, payload.ok === false ? 400 : 200, payload);
      }

      if (parsedUrl.pathname === '/api/cases') {
        const query = parsedUrl.query.q || '';
        return sendJson(res, 200, dataSource.searchCases(query));
      }

      if (parsedUrl.pathname === '/api/search') {
        const query = parsedUrl.query.q || '';
        return sendJson(res, 200, dataSource.search(query));
      }

      if (parsedUrl.pathname === '/api/term') {
        const payload = dataSource.getTerm(parsedUrl.query.id);
        if (!payload) {
          return sendJson(res, 404, { ok: false, message: 'Term not found' });
        }
        return sendJson(res, 200, payload);
      }

      if (parsedUrl.pathname === '/api/case') {
        const payload = dataSource.getCase(parsedUrl.query.id);
        if (!payload) {
          return sendJson(res, 404, { ok: false, message: 'Case not found' });
        }
        return sendJson(res, 200, payload);
      }

      if (parsedUrl.pathname === '/api/terms') {
        return sendJson(res, 200, dataSource.getTerms());
      }

      return sendJson(res, 404, { ok: false, message: 'API not found' });
    } catch (error) {
      return sendJson(res, 500, {
        ok: false,
        message: 'Internal Server Error',
        detail: error.message,
      });
    }
  }

  return http.createServer((req, res) => {
    try {
      const requestUrl = new URL(req.url, 'http://localhost');
      const queryValues = {};
      for (const [key, value] of requestUrl.searchParams.entries()) {
        if (!queryValues[key]) queryValues[key] = [];
        queryValues[key].push(value);
      }
      const parsedUrl = {
        pathname: requestUrl.pathname,
        query: Object.fromEntries(requestUrl.searchParams),
        queryValues,
      };

      if (parsedUrl.pathname.startsWith('/api/')) {
        return handleApi(req, res, parsedUrl);
      }

      const page = resolvePage(requestUrl);
      if (page?.file) {
        return sendFile(res, path.join(config.WEB_DIR, page.file), html =>
          html.replace('<!--site-navigation-->', renderNavigation(parsedUrl.pathname)));
      }
      if (parsedUrl.pathname.startsWith('/assets/') || parsedUrl.pathname.startsWith('/media/')) {
        return sendFile(res, resolveStaticFile(parsedUrl.pathname));
      }
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      return res.end('页面不存在');
    } catch (error) {
      return sendJson(res, 500, {
        ok: false,
        message: 'Internal Server Error',
        detail: error.message,
      });
    }
  });
}

function startServer() {
  const server = createServer();

  server.listen(config.PORT, () => {
    const dataSource = createDataSource(config);
    let sourceLabel = config.SOURCE_MODE;

    try {
      sourceLabel = dataSource.getHealth().sourceLabel;
    } catch {
      sourceLabel = config.SOURCE_MODE;
    }

    console.log(`Demo server running at http://localhost:${config.PORT}`);
    console.log(`Data source: ${sourceLabel}`);
  });

  return server;
}

module.exports = {
  createServer,
  startServer,
};

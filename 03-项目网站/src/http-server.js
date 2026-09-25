const fs = require('fs');
const http = require('http');
const path = require('path');
const config = require('./config');
const { analyzeWithAnnotationAi } = require('./ai-annotation');
const { browseAnnotations, buildAnnotationBootstrap } = require('./annotation-browser');
const { createDataSource } = require('./data-source');
const { getV2Acceptance } = require('./v2-acceptance');
const { retrieveForCase, retrieveFromCorpus } = require('./v2-retrieval');
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

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, no-cache, must-revalidate',
    'Pragma': 'no-cache',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  });
  res.end(JSON.stringify(payload, null, 2));
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';

    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > 128000) {
        reject(new Error('Request body too large'));
        req.destroy();
      }
    });

    req.on('end', () => {
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

function sendFile(res, filePath) {
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
    res.end(fs.readFileSync(filePath));
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

  if (requestPath.startsWith('/data/')) {
    const dataPath = safeResolve(config.DATA_DIR, requestPath.slice('/data/'.length));
    return dataPath || path.join(config.WEB_DIR, '404.not-found');
  }

  let relativePath = requestPath;
  if (relativePath.startsWith('/web/')) {
    relativePath = relativePath.slice('/web'.length);
  }

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

      if (parsedUrl.pathname === '/api/annotation') {
        return sendJson(res, 200, browseAnnotations(config, {
          query: parsedUrl.query.q || '',
          document: parsedUrl.query.document,
          method: parsedUrl.query.method,
          annotator: parsedUrl.query.annotator,
          origin: parsedUrl.query.origin,
          page: parsedUrl.query.page,
          pageSize: parsedUrl.query.pageSize,
        }));
      }

      if (parsedUrl.pathname === '/api/v2/summary') {
        if (req.method !== 'GET') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        return sendJson(res, 200, await getCachedV2Summary(config));
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

      if (parsedUrl.pathname === '/api/v2/retrieve') {
        if (req.method !== 'GET') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }
        const caseId = parsedUrl.query.case_id || '';
        const limit = Number(parsedUrl.query.limit || 8);
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
        const query = parsedUrl.query.q || '';
        const workKey = parsedUrl.query.work_key || '';
        const includeCases = ['1', 'true', 'yes'].includes(String(parsedUrl.query.include_cases || '').toLowerCase());
        if (!query.trim()) {
          return sendJson(res, 400, { ok: false, message: 'case_id_or_query_required' });
        }
        return sendJson(res, 200, await retrieveFromCorpus(config, {
          query,
          workKey,
          limit,
          includeCases,
        }));
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

      if (parsedUrl.pathname === '/api/ai/annotation') {
        if (req.method !== 'POST') {
          return sendJson(res, 405, { ok: false, message: 'Method Not Allowed' });
        }

        const body = await readJsonBody(req);
        const result = await analyzeWithAnnotationAi(config, dataSource, body.question || body.text || '');
        return sendJson(res, result.status, result.payload);
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
      const parsedUrl = {
        pathname: requestUrl.pathname,
        query: Object.fromEntries(requestUrl.searchParams),
      };

      if (parsedUrl.pathname.startsWith('/api/')) {
        return handleApi(req, res, parsedUrl);
      }

      return sendFile(res, resolveStaticFile(parsedUrl.pathname));
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

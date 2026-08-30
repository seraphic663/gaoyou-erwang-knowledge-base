const fs = require('fs');
const http = require('http');
const path = require('path');
const config = require('./config');
const { analyzeWithAnnotationAi } = require('./ai-annotation');
const { browseAnnotations, buildAnnotationBootstrap } = require('./annotation-browser');
const { createDataSource } = require('./data-source');
const { getV2Acceptance } = require('./v2-acceptance');
const { getV2ReviewTasks, getV2ReviewTask, submitV2Review } = require('./v2-review');

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
  return [
    config.V2_DB_FILE,
    path.join(config.WORKSPACE_ROOT, 'v2', 'data', 'real_runs', 'v2_validation_report.json'),
    path.join(config.WORKSPACE_ROOT, 'v2', 'data', 'real_runs', 'review_tasks', 'review_task_manifest.review.v1.json'),
    path.join(config.WORKSPACE_ROOT, 'v2', 'data', 'real_runs', 'work_queues_report.json'),
  ].map(fileRevision).join('|');
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, no-cache, must-revalidate',
    'Pragma': 'no-cache',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
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

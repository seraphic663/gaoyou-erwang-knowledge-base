const fs = require('fs');
const http = require('http');
const path = require('path');
const url = require('url');
const config = require('./config');
const { createDataSource } = require('./data-source');

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(JSON.stringify(payload, null, 2));
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

  let relativePath = requestPath;
  if (relativePath.startsWith('/web/')) {
    relativePath = relativePath.slice('/web'.length);
  }

  const staticPath = safeResolve(config.WEB_DIR, relativePath);
  return staticPath || path.join(config.WEB_DIR, '404.not-found');
}

function createServer() {
  const dataSource = createDataSource(config);

  function handleApi(req, res, parsedUrl) {
    try {
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
        }));
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
      const parsedUrl = url.parse(req.url, true);

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

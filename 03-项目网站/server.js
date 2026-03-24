const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT || 3000;
const ROOT = __dirname;
const WORKSPACE_ROOT = path.resolve(ROOT, '..');
const WEB_DIR = fs.existsSync(path.join(ROOT, 'index.html')) ? ROOT : path.join(ROOT, 'web');
const DATA_DIR = fs.existsSync(path.join(ROOT, 'data')) ? path.join(ROOT, 'data') : path.join(WORKSPACE_ROOT, 'data');
const MEDIA_DIR = fs.existsSync(path.join(ROOT, 'media')) ? path.join(ROOT, 'media') : path.join(WORKSPACE_ROOT, 'media');
const DB_FILE = path.join(DATA_DIR, 'demo-db.json');

const STORE_DEFINITIONS = [
  {
    name: 'works',
    label: '文献表',
    purpose: '记录《王氏四种》及相关版本信息。',
    keyFields: ['id', 'title', 'author', 'version'],
    indexes: ['category'],
  },
  {
    name: 'passages',
    label: '原文段落表',
    purpose: '存放 OCR/校对后的原文片段与页码定位。',
    keyFields: ['id', 'workId', 'volume', 'page'],
    indexes: ['workId'],
  },
  {
    name: 'terms',
    label: '词条表',
    purpose: '存放检字对象、别名与古音信息。',
    keyFields: ['id', 'term', 'phonology'],
    indexes: ['category'],
  },
  {
    name: 'cases',
    label: '考释案例表',
    purpose: '记录发疑—取证—释理—结论的完整考据链。',
    keyFields: ['id', 'termId', 'title', 'status'],
    indexes: ['termId', 'workId', 'status'],
  },
  {
    name: 'evidences',
    label: '证据表',
    purpose: '存放书证、引文、位置与证据类型。',
    keyFields: ['id', 'caseId', 'sourceWorkId', 'passageId'],
    indexes: ['caseId', 'sourceWorkId', 'passageId'],
  },
  {
    name: 'relations',
    label: '关系表',
    purpose: '存放通假、同源、对文、双声等结构化关系。',
    keyFields: ['id', 'fromType', 'toType', 'relationType'],
    indexes: ['fromType', 'fromId', 'toType', 'toId', 'relationType'],
  },
];

const SEED_DB = {
  schemaVersion: 1,
  tables: {
    works: [
      { id: 1, title: '广雅疏证', author: '王念孙', version: '家刻本 / 点校本', category: '训诂总集', note: '以因声求义疏证《广雅》。' },
      { id: 2, title: '读书杂志', author: '王念孙', version: '通行点校本', category: '校勘札记', note: '涉及《逸周书》《史记》等校读。' },
      { id: 3, title: '经义述闻', author: '王引之', version: '通行点校本', category: '经学札记', note: '汇集父子二人训诂成果。' },
      { id: 4, title: '经传释词', author: '王引之', version: '通行点校本', category: '虚词研究', note: '系统研究上古汉语虚词。' },
    ],
    passages: [
      { id: 1, workId: 3, volume: '卷三', page: 'P45', originalText: '犹豫，双声字也，字或作犹与。', normalizedText: '犹豫，双声字也，字或作犹与。', keywords: ['犹豫', '犹与', '双声'] },
      { id: 2, workId: 3, volume: '卷八', page: 'P126', originalText: '不我知，谓不知我也。', normalizedText: '不我知，谓不知我也。', keywords: ['不我知', '宾语前置'] },
      { id: 3, workId: 4, volume: '卷二', page: 'P33', originalText: '术字乐甫，术通遂，遂训安。', normalizedText: '术字乐甫，术通遂，遂训安。', keywords: ['术', '遂', '乐甫'] },
    ],
    terms: [
      { id: 1, term: '犹豫', aliases: ['犹与', '夷犹', '容与'], phonology: '双声联绵词 / 一声之转', category: '联绵词', gloss: '表示迟疑、徘徊之义。' },
      { id: 2, term: '能不我知', aliases: ['不我知', '能通而'], phonology: '能 / 而 古通', category: '通假与句法', gloss: '说明宾语前置与字通现象。' },
      { id: 3, term: '术字乐甫', aliases: ['遂', '安', '乐'], phonology: '形音义互证', category: '名与字', gloss: '用于展示词义递进和名字关系。' },
    ],
    cases: [
      { id: 1, termId: 1, workId: 3, title: '双声词考释：犹豫', problem: '如何解释犹豫、犹与、夷犹、容与之间的关系？', method: '一声之转 / 联绵词', steps: ['旁征引书证', '比较同义连绵词', '判断为一声之转'], conclusion: '犹豫与犹与、夷犹、容与同属一组联绵词，义存乎声。', status: 'published' },
      { id: 2, termId: 2, workId: 3, title: '句法与通假：能不我知', problem: '为何旧注会把“能”解释得不准确？', method: '宾语前置 + 古字通', steps: ['辨析不我知的句法', '确认宾语前置', '说明能通而'], conclusion: '此处应释为“不知我”，“能”宜训“而”。', status: 'published' },
      { id: 3, termId: 3, workId: 4, title: '名与字关系：宋公子术字乐甫', problem: '“术”、“遂”、“安”、“乐”如何互证？', method: '形音义互证', steps: ['术通遂', '遂训安', '安与乐通'], conclusion: '遂与乐相通，名与字的关系可由音义链条贯通。', status: 'draft' },
    ],
    evidences: [
      { id: 1, caseId: 1, sourceWorkId: 3, passageId: 1, quote: '犹豫，双声字也，字或作犹与。', type: '书证', location: '《经义述闻》卷三' },
      { id: 2, caseId: 2, sourceWorkId: 3, passageId: 2, quote: '不我知，谓不知我也。', type: '句法证据', location: '《经义述闻》卷八' },
      { id: 3, caseId: 3, sourceWorkId: 4, passageId: 3, quote: '术通遂，遂训安。', type: '字形与音义证据', location: '《经传释词》卷二' },
    ],
    relations: [
      { id: 1, fromType: 'term', fromId: 1, toType: 'term', toId: 1, relationType: '一声之转', description: '犹豫与犹与、夷犹、容与构成同组词链。', confidence: 0.96 },
      { id: 2, fromType: 'term', fromId: 2, toType: 'case', toId: 2, relationType: '对应案例', description: '“能不我知”对应句法与通假案例。', confidence: 0.94 },
      { id: 3, fromType: 'case', fromId: 1, toType: 'evidence', toId: 1, relationType: '证据支撑', description: '案例 1 由《经义述闻》卷三书证支撑。', confidence: 0.98 },
      { id: 4, fromType: 'case', fromId: 2, toType: 'evidence', toId: 2, relationType: '证据支撑', description: '案例 2 由句法判断与书证共同支撑。', confidence: 0.97 },
      { id: 5, fromType: 'case', fromId: 3, toType: 'evidence', toId: 3, relationType: '证据支撑', description: '案例 3 由字形与音义链条支撑。', confidence: 0.95 },
    ],
  },
};

function ensureDatabaseFile() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(DB_FILE)) {
    fs.writeFileSync(DB_FILE, JSON.stringify(SEED_DB, null, 2), 'utf8');
  }
}

function loadDatabase() {
  ensureDatabaseFile();
  try {
    const raw = fs.readFileSync(DB_FILE, 'utf8');
    const db = JSON.parse(raw.replace(/^\uFEFF/, ''));
    if (!db || typeof db !== 'object' || !db.tables) {
      throw new Error('Invalid database schema');
    }
    return db;
  } catch {
    const backup = `${DB_FILE}.broken.${Date.now()}`;
    if (fs.existsSync(DB_FILE)) {
      fs.copyFileSync(DB_FILE, backup);
    }
    saveDatabase(SEED_DB);
    return JSON.parse(JSON.stringify(SEED_DB));
  }
}

function saveDatabase(db) {
  fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2), 'utf8');
}

function getWorkMap(db) {
  return new Map(db.tables.works.map((item) => [item.id, item]));
}

function getTermMap(db) {
  return new Map(db.tables.terms.map((item) => [item.id, item]));
}

function getEvidenceMap(db) {
  return new Map(db.tables.evidences.map((item) => [item.id, item]));
}

function enrichCase(db, item) {
  const workMap = getWorkMap(db);
  const termMap = getTermMap(db);
  const evidenceMap = getEvidenceMap(db);
  const caseEvidences = db.tables.evidences.filter((evidence) => evidence.caseId === item.id);

  return {
    ...item,
    workTitle: workMap.get(item.workId)?.title || '',
    termName: termMap.get(item.termId)?.term || '',
    evidenceCount: caseEvidences.length,
    evidenceQuotes: caseEvidences.map((evidence) => evidenceMap.get(evidence.id)?.quote || evidence.quote),
  };
}

function searchCases(db, query) {
  const keyword = String(query || '').trim().toLowerCase();
  const enriched = db.tables.cases.map((item) => enrichCase(db, item));
  if (!keyword) return enriched;

  return enriched.filter((item) => {
    const text = [
      item.title,
      item.problem,
      item.method,
      item.steps.join(' '),
      item.conclusion,
      item.status,
      item.termName,
      item.workTitle,
      item.evidenceQuotes.join(' '),
    ]
      .join(' ')
      .toLowerCase();
    return text.includes(keyword);
  });
}

function buildCounts(db) {
  return Object.fromEntries(Object.entries(db.tables).map(([name, records]) => [name, records.length]));
}

function buildBootstrap(db) {
  const counts = buildCounts(db);
  const totalRecords = Object.values(counts).reduce((sum, value) => sum + value, 0);
  return {
    ok: true,
    schemaVersion: db.schemaVersion,
    counts,
    totalRecords,
    stores: STORE_DEFINITIONS.map((storeDefinition) => ({
      ...storeDefinition,
      count: counts[storeDefinition.name] || 0,
    })),
    featuredCases: db.tables.cases.map((item) => enrichCase(db, item)),
    sampleTerms: db.tables.terms,
  };
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(JSON.stringify(payload, null, 2));
}

function sendFile(res, filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const types = {
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
    const data = fs.readFileSync(filePath);
    res.writeHead(200, { 'Content-Type': types[ext] || 'application/octet-stream' });
    res.end(data);
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
  if (requestPath === '/') return path.join(WEB_DIR, 'index.html');

  if (requestPath.startsWith('/media/')) {
    const mediaPath = safeResolve(MEDIA_DIR, requestPath.slice('/media/'.length));
    return mediaPath || path.join(WEB_DIR, '404.not-found');
  }

  let relativePath = requestPath;
  if (relativePath.startsWith('/web/')) {
    relativePath = relativePath.slice('/web'.length);
  }
  const staticPath = safeResolve(WEB_DIR, relativePath);
  return staticPath || path.join(WEB_DIR, '404.not-found');
}

function handleApi(req, res, parsedUrl) {
  const db = loadDatabase();

  if (parsedUrl.pathname === '/api/health') {
    return sendJson(res, 200, {
      ok: true,
      service: 'gaoyou-erwang-demo',
      uptimeSec: Math.round(process.uptime()),
      dbFile: DB_FILE,
      time: new Date().toISOString(),
    });
  }

  if (parsedUrl.pathname === '/api/bootstrap') {
    return sendJson(res, 200, buildBootstrap(db));
  }

  if (parsedUrl.pathname === '/api/schema') {
    const counts = buildCounts(db);
    return sendJson(res, 200, {
      ok: true,
      stores: STORE_DEFINITIONS.map((storeDefinition) => ({
        ...storeDefinition,
        count: counts[storeDefinition.name] || 0,
      })),
      counts,
    });
  }

  if (parsedUrl.pathname === '/api/cases') {
    const query = parsedUrl.query.q || '';
    return sendJson(res, 200, {
      ok: true,
      query,
      items: searchCases(db, query),
    });
  }

  if (parsedUrl.pathname === '/api/terms') {
    return sendJson(res, 200, { ok: true, items: db.tables.terms });
  }

  return sendJson(res, 404, { ok: false, message: 'API not found' });
}

const server = http.createServer((req, res) => {
  try {
    const parsedUrl = url.parse(req.url, true);

    if (parsedUrl.pathname.startsWith('/api/')) {
      return handleApi(req, res, parsedUrl);
    }

    const filePath = resolveStaticFile(parsedUrl.pathname);
    return sendFile(res, filePath);
  } catch {
    return sendJson(res, 500, { ok: false, message: 'Internal Server Error' });
  }
});

server.listen(PORT, () => {
  ensureDatabaseFile();
  console.log(`Demo server running at http://localhost:${PORT}`);
});

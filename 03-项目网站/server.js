const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT || 3000;
const ROOT = __dirname;
const WORKSPACE_ROOT = path.resolve(ROOT, '..');
const WEB_DIR = fs.existsSync(path.join(ROOT, 'index.html')) ? ROOT : path.join(ROOT, 'web');
const DATA_DIR = (() => {
  const explicitDataDir = process.env.DATA_DIR || process.env.DATABASE_DIR;
  if (explicitDataDir) {
    return path.isAbsolute(explicitDataDir) ? explicitDataDir : path.resolve(ROOT, explicitDataDir);
  }

  const railwayVolumeDir = process.env.RAILWAY_VOLUME_MOUNT_PATH;
  if (railwayVolumeDir) {
    return railwayVolumeDir;
  }

  if (fs.existsSync(path.join(ROOT, 'data'))) {
    return path.join(ROOT, 'data');
  }

  return path.join(WORKSPACE_ROOT, 'data');
})();
const MEDIA_DIR = fs.existsSync(path.join(ROOT, 'media')) ? path.join(ROOT, 'media') : path.join(WORKSPACE_ROOT, 'media');
const DB_FILE = path.join(DATA_DIR, 'demo-db.json');

const STORE_DEFINITIONS = [
  {
    name: 'works',
    label: '著作表',
    purpose: '记录二王著作、原始经典与工具书，是所有文本与案例的上层来源表。',
    keyFields: ['id', 'title', 'author', 'workType'],
    indexes: ['workType', 'dynasty'],
    fields: [
      { name: 'id', description: '主键，唯一标识一部书。' },
      { name: 'title', description: '书名，用于展示和检索。' },
      { name: 'author', description: '作者或主要责任者。' },
      { name: 'workType', description: '文献类型：二王著作、原始经典、工具书等。' },
      { name: 'dynasty', description: '朝代信息，便于按时间背景筛选。' },
      { name: 'timeNote', description: '写作或成书时间说明，当前先用文本记录。' },
      { name: 'notes', description: '补充说明，如学术性质、用途等。' },
    ],
  },
  {
    name: 'passages',
    label: '文本片段表',
    purpose: '记录可以被准确定位的文本片段，当前以条目、段落、引文片段为主。',
    keyFields: ['id', 'workId', 'juan', 'passageType'],
    indexes: ['workId', 'passageType'],
    fields: [
      { name: 'id', description: '主键。' },
      { name: 'workId', description: '所属著作，对应 works.id。' },
      { name: 'juan', description: '卷次；无卷次时可为空。' },
      { name: 'chapter', description: '篇、章、类目等较高层级定位。' },
      { name: 'locationNote', description: '更细位置说明，如条目号、页码、行号。' },
      { name: 'rawText', description: '原始录入文本，尽量贴近底本。' },
      { name: 'normalizedText', description: '规范化文本，便于统一检索。' },
      { name: 'passageType', description: '片段类型：二王论述、原始经典、引证材料。' },
    ],
  },
  {
    name: 'terms',
    label: '词条表',
    purpose: '记录检索词和方法术语，当前将字词对象与术语对象合并管理。',
    keyFields: ['id', 'term', 'termType'],
    indexes: ['termType', 'category'],
    fields: [
      { name: 'id', description: '主键。' },
      { name: 'term', description: '词条本体，如“犹豫”“一声之转”。' },
      { name: 'termType', description: '类型：字、词、术语。' },
      { name: 'category', description: '分类标签，如联绵词、句法现象、方法术语。' },
      { name: 'aliases', description: '别名、异体或相关写法。' },
      { name: 'notes', description: '补充说明，如定义、音义摘要。' },
    ],
  },
  {
    name: 'cases',
    label: '考释案例表',
    purpose: '一条记录对应一则完整考据，连接二王论述、原始经典、方法和结论。',
    keyFields: ['id', 'title', 'erwangPassageId', 'targetPassageId'],
    indexes: ['termId', 'certainty', 'status'],
    fields: [
      { name: 'id', description: '主键。' },
      { name: 'title', description: '案例标题，建议写成“问题类型 + 对象”。' },
      { name: 'termId', description: '主要关联词条，对应 terms.id。' },
      { name: 'erwangPassageId', description: '二王论述所在片段，对应 passages.id。' },
      { name: 'targetPassageId', description: '被解释原文所在片段，对应 passages.id。' },
      { name: 'problem', description: '问题触发点，即哪里不通或可疑。' },
      { name: 'method', description: '当前案例的主方法，如改义、通假、改形。' },
      { name: 'processText', description: '考据过程全文说明；最小版先整体保存。' },
      { name: 'conclusion', description: '最终结论。' },
      { name: 'certainty', description: '置信状态：确定、可疑、待核、多解。' },
      { name: 'status', description: '数据状态：草稿、已校对、已审核。' },
    ],
  },
  {
    name: 'evidences',
    label: '证据表',
    purpose: '一条记录对应一条证据，用来支撑某个考据案例。',
    keyFields: ['id', 'caseId', 'sourcePassageId', 'evidenceType'],
    indexes: ['caseId', 'sourcePassageId', 'evidenceType'],
    fields: [
      { name: 'id', description: '主键。' },
      { name: 'caseId', description: '所属案例，对应 cases.id。' },
      { name: 'sourcePassageId', description: '证据来源片段，对应 passages.id。' },
      { name: 'evidenceType', description: '证据类型：书证、音证、义证、形证、语法证据。' },
      { name: 'quoteText', description: '实际引文，可为来源片段的关键部分。' },
      { name: 'note', description: '证据解释，说明为何能支撑该案例。' },
    ],
  },
];

const SEED_DB = {
  schemaVersion: 2,
  tables: {
    works: [
      { id: 1, title: '经义述闻', author: '王引之', workType: '二王著作', dynasty: '清', timeNote: '清嘉庆间成书', notes: '汇集父子二人训诂成果。' },
      { id: 2, title: '经传释词', author: '王引之', workType: '二王著作', dynasty: '清', timeNote: '清嘉庆间刊行', notes: '系统研究上古汉语虚词。' },
      { id: 3, title: '诗经', author: '佚名', workType: '原始经典', dynasty: '先秦', timeNote: '西周至春秋时期形成', notes: '二王常据以展开经义考证。' },
      { id: 4, title: '左传', author: '左丘明旧题', workType: '原始经典', dynasty: '先秦', timeNote: '战国至两汉间传世', notes: '常作为名物、句法与训释书证来源。' },
      { id: 5, title: '尔雅', author: '佚名', workType: '工具书', dynasty: '先秦至两汉', timeNote: '早期训诂辞书', notes: '用作义项和训释证据。' },
    ],
    passages: [
      { id: 1, workId: 1, juan: '卷三', chapter: '', locationNote: '条目“犹豫”', rawText: '犹豫，双声字也，字或作犹与。', normalizedText: '犹豫，双声字也，字或作犹与。', passageType: '二王论述' },
      { id: 2, workId: 1, juan: '卷八', chapter: '', locationNote: '条目“不我知”', rawText: '不我知，谓不知我也。', normalizedText: '不我知，谓不知我也。', passageType: '二王论述' },
      { id: 3, workId: 2, juan: '卷二', chapter: '', locationNote: '条目“术字乐甫”', rawText: '术字乐甫，术通遂，遂训安。', normalizedText: '术字乐甫，术通遂，遂训安。', passageType: '二王论述' },
      { id: 4, workId: 3, juan: '《王风》', chapter: '黍离', locationNote: '相关句法讨论背景', rawText: '知我者谓我心忧，不知我者谓我何求。', normalizedText: '知我者谓我心忧，不知我者谓我何求。', passageType: '原始经典' },
      { id: 5, workId: 4, juan: '昭公二十年', chapter: '', locationNote: '宋公子术字乐甫相关背景', rawText: '宋公子城字子朱，公子地字子仲，公子术字乐甫。', normalizedText: '宋公子城字子朱，公子地字子仲，公子术字乐甫。', passageType: '原始经典' },
      { id: 6, workId: 5, juan: '', chapter: '释诂', locationNote: '训释书证', rawText: '与，犹也。', normalizedText: '与，犹也。', passageType: '引证材料' },
    ],
    terms: [
      { id: 1, term: '犹豫', termType: '词', category: '联绵词', aliases: ['犹与', '夷犹', '容与'], notes: '与双声、一声之转相关。' },
      { id: 2, term: '不我知', termType: '词', category: '句法现象', aliases: ['不知我'], notes: '常与宾语前置和旧注误释问题关联。' },
      { id: 3, term: '术字乐甫', termType: '词', category: '名与字', aliases: ['术', '遂', '安', '乐'], notes: '用于展示音义链条和名字号互证。' },
      { id: 4, term: '一声之转', termType: '术语', category: '方法术语', aliases: [], notes: '二王常用的方法术语之一。' },
    ],
    cases: [
      { id: 1, title: '双声词考释：犹豫', termId: 1, erwangPassageId: 1, targetPassageId: null, problem: '如何解释“犹豫”与“犹与”“夷犹”“容与”的关系？', method: '联绵词 / 一声之转', processText: '先指出“犹豫”为双声字，随后旁征“犹与”“夷犹”“容与”等相关词形，再结合训释书证说明其义相通，最后判定为同组联绵词。', conclusion: '犹豫与犹与、夷犹、容与可视为同组词形，义存乎声。', certainty: '确定', status: '已审核' },
      { id: 2, title: '句法与训释：不我知', termId: 2, erwangPassageId: 2, targetPassageId: 4, problem: '旧注将相关句式解释得过于牵强，需先判断句法再处理字义。', method: '句法分析 / 改义', processText: '先辨析“不我知”为否定句宾语前置，再回到句意说明应读作“不知我”，从而修正旧注误解。', conclusion: '应先按宾语前置句式理解，再作“不知我”的训释。', certainty: '确定', status: '已审核' },
      { id: 3, title: '名与字关系：宋公子术字乐甫', termId: 3, erwangPassageId: 3, targetPassageId: 5, problem: '“术”“遂”“安”“乐”如何构成可追溯的音义链条？', method: '形音义互证', processText: '从“术通遂”入手，再以“遂训安”推进，最后说明“安”与“乐”相通，借此贯通名与字之间的关系。', conclusion: '可通过“术—遂—安—乐”的链条解释名与字的对应关系。', certainty: '待核', status: '草稿' },
    ],
    evidences: [
      { id: 1, caseId: 1, sourcePassageId: 1, evidenceType: '书证', quoteText: '犹豫，双声字也，字或作犹与。', note: '直接说明“犹豫”与“犹与”的词形关系。' },
      { id: 2, caseId: 1, sourcePassageId: 6, evidenceType: '义证', quoteText: '与，犹也。', note: '提供训释辞书中的义项支撑。' },
      { id: 3, caseId: 2, sourcePassageId: 2, evidenceType: '语法证据', quoteText: '不我知，谓不知我也。', note: '直接给出对宾语前置句式的解释。' },
      { id: 4, caseId: 3, sourcePassageId: 3, evidenceType: '义证', quoteText: '术通遂，遂训安。', note: '展示“术—遂—安”的中间链条。' },
    ],
  },
};

function ensureDatabaseFile() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(DB_FILE)) {
    fs.writeFileSync(DB_FILE, JSON.stringify(SEED_DB, null, 2), 'utf8');
    return;
  }

  try {
    const raw = fs.readFileSync(DB_FILE, 'utf8');
    const parsed = JSON.parse(raw.replace(/^\uFEFF/, ''));
    const tableNames = Object.keys(parsed?.tables || {});
    const isLatestSchema =
      parsed?.schemaVersion === SEED_DB.schemaVersion &&
      ['works', 'passages', 'terms', 'cases', 'evidences'].every((name) => tableNames.includes(name)) &&
      !tableNames.includes('relations');

    if (!isLatestSchema) {
      fs.writeFileSync(DB_FILE, JSON.stringify(SEED_DB, null, 2), 'utf8');
    }
  } catch {
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

function getPassageMap(db) {
  return new Map(db.tables.passages.map((item) => [item.id, item]));
}

function enrichCase(db, item) {
  const workMap = getWorkMap(db);
  const passageMap = getPassageMap(db);
  const termMap = getTermMap(db);
  const evidenceMap = getEvidenceMap(db);
  const caseEvidences = db.tables.evidences.filter((evidence) => evidence.caseId === item.id);
  const erwangPassage = passageMap.get(item.erwangPassageId);
  const targetPassage = passageMap.get(item.targetPassageId);
  const erwangWork = erwangPassage ? workMap.get(erwangPassage.workId) : null;
  const targetWork = targetPassage ? workMap.get(targetPassage.workId) : null;

  return {
    ...item,
    termName: termMap.get(item.termId)?.term || '',
    erwangWorkTitle: erwangWork?.title || '',
    targetWorkTitle: targetWork?.title || '',
    erwangLocation: erwangPassage ? [erwangPassage.juan, erwangPassage.chapter, erwangPassage.locationNote].filter(Boolean).join(' · ') : '',
    targetLocation: targetPassage ? [targetPassage.juan, targetPassage.chapter, targetPassage.locationNote].filter(Boolean).join(' · ') : '',
    evidenceCount: caseEvidences.length,
    evidenceQuotes: caseEvidences.map((evidence) => evidenceMap.get(evidence.id)?.quoteText || evidence.quoteText),
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
      item.processText,
      item.conclusion,
      item.certainty,
      item.status,
      item.termName,
      item.erwangWorkTitle,
      item.targetWorkTitle,
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
  console.log(`Database file: ${DB_FILE}`);
});

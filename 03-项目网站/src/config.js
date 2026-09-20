const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.resolve(__dirname, '..');
const WORKSPACE_ROOT = path.resolve(ROOT_DIR, '..');
loadEnvFile(path.join(WORKSPACE_ROOT, '.env'));
loadEnvFile(path.join(ROOT_DIR, '.env'));
const PORT = Number(process.env.PORT || 3000);

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;

  const lines = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/);
  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return;

    const match = /^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(trimmed);
    if (!match || process.env[match[1]]) return;

    process.env[match[1]] = match[2].replace(/^["']|["']$/g, '');
  });
}

function resolveWebDir() {
  if (fs.existsSync(path.join(ROOT_DIR, 'index.html'))) {
    return ROOT_DIR;
  }

  return path.join(ROOT_DIR, 'web');
}

function resolveDataDir() {
  const explicitDataDir = process.env.DATA_DIR || process.env.DATABASE_DIR;
  if (explicitDataDir) {
    return path.isAbsolute(explicitDataDir)
      ? explicitDataDir
      : path.resolve(ROOT_DIR, explicitDataDir);
  }

  const railwayVolumeDir = process.env.RAILWAY_VOLUME_MOUNT_PATH;
  if (railwayVolumeDir) {
    return railwayVolumeDir;
  }

  if (fs.existsSync(path.join(ROOT_DIR, 'data'))) {
    return path.join(ROOT_DIR, 'data');
  }

  return path.join(WORKSPACE_ROOT, 'data');
}

function resolveMediaDir() {
  if (fs.existsSync(path.join(ROOT_DIR, 'media'))) {
    return path.join(ROOT_DIR, 'media');
  }

  return path.join(WORKSPACE_ROOT, 'media');
}

function resolveSourceMode() {
  const explicit = String(process.env.DATA_SOURCE || '').trim().toLowerCase();
  if (explicit === 'demo' || explicit === 'sqlite') {
    return explicit;
  }

  if (fs.existsSync(path.join(resolveDataDir(), 'sqlite-snapshot.json'))) {
    return 'sqlite';
  }

  return 'demo';
}

const DATA_DIR = resolveDataDir();

function isRailwayRuntime() {
  return Boolean(
    process.env.RAILWAY_ENVIRONMENT
      || process.env.RAILWAY_PROJECT_ID
      || process.env.RAILWAY_SERVICE_ID
      || process.env.RAILWAY_VOLUME_MOUNT_PATH,
  );
}

function resolveConfiguredPath(value, fallbackRoot) {
  if (!value) return null;
  return path.isAbsolute(value) ? value : path.resolve(fallbackRoot, value);
}

function resolveV2DbFile() {
  const explicit = resolveConfiguredPath(process.env.V2_DB_FILE, ROOT_DIR);
  if (explicit) return explicit;

  const mode = String(process.env.V2_DB_MODE || 'auto').trim().toLowerCase();
  const useProduction = mode === 'production'
    || (mode === 'auto' && isRailwayRuntime());
  if (useProduction) {
    const dataRoot = process.env.RAILWAY_VOLUME_MOUNT_PATH
      || path.join(WORKSPACE_ROOT, 'v2', 'data');
    return path.join(dataRoot, 'real_runs', 'annotation_v2.db');
  }

  return path.join(WORKSPACE_ROOT, 'v2', 'data', 'local_test', 'annotation_v2.local.db');
}

const V2_DB_FILE = resolveV2DbFile();
const V2_DB_DIR = path.dirname(V2_DB_FILE);

function resolveV2CorpusDbFile() {
  const explicit = resolveConfiguredPath(process.env.V2_CORPUS_DB_FILE, ROOT_DIR);
  if (explicit) return explicit;
  if (isRailwayRuntime()) return V2_DB_FILE;

  const localCorpus = path.join(WORKSPACE_ROOT, 'v2', 'data', 'real_runs', 'annotation_v2.db');
  if (fs.existsSync(localCorpus)) return localCorpus;
  return V2_DB_FILE;
}

const V2_CORPUS_DB_FILE = resolveV2CorpusDbFile();
const V2_DB_MODE = String(process.env.V2_DB_MODE || 'auto').trim().toLowerCase();
const V2_DB_PROFILE = isRailwayRuntime() || V2_DB_MODE === 'production'
  ? 'production'
  : 'local-test';

function resolveFlag(name, fallback = false) {
  if (process.env[name] !== undefined) return process.env[name] === '1';
  return fallback;
}

module.exports = {
  ROOT_DIR,
  WORKSPACE_ROOT,
  WEB_DIR: resolveWebDir(),
  DATA_DIR,
  MEDIA_DIR: resolveMediaDir(),
  PORT,
  PYTHON_BIN: process.env.PYTHON_BIN || process.env.PYTHON || 'python',
  SOURCE_MODE: resolveSourceMode(),
  DEMO_DB_FILE: path.join(DATA_DIR, 'demo-db.json'),
  SQLITE_SNAPSHOT_FILE: path.join(DATA_DIR, 'sqlite-snapshot.json'),
  ANNOTATION_SNAPSHOT_FILE: path.join(DATA_DIR, 'annotation-snapshot.json'),
  SQLITE_DB_FILE: path.join(WORKSPACE_ROOT, '02-数据库', 'data', 'dictionary.db'),
  ANNOTATION_DB_FILE: path.join(WORKSPACE_ROOT, '02-数据库', 'data', 'annotations.db'),
  SQLITE_BRIDGE_FILE: path.join(ROOT_DIR, 'scripts', 'sqlite_bridge.py'),
  V2_DB_FILE,
  V2_DB_DIR,
  V2_CORPUS_DB_FILE,
  V2_DB_MODE,
  V2_DB_PROFILE,
  V2_ACCEPTANCE_BRIDGE_FILE: path.join(ROOT_DIR, 'scripts', 'v2_acceptance_bridge.py'),
  V2_RETRIEVAL_BRIDGE_FILE: path.join(WORKSPACE_ROOT, 'v2', 'scripts', 'v2_retrieval_bridge.py'),
  V2_REVIEW_BRIDGE_FILE: path.join(WORKSPACE_ROOT, 'v2', 'scripts', 'v2_review_bridge.py'),
  V2_FIVE_STEP_AUDIT_BRIDGE_FILE: path.join(WORKSPACE_ROOT, 'v2', 'scripts', 'v2_five_step_audit_bridge.py'),
  V2_REVIEW_MANIFEST_FILE: process.env.V2_REVIEW_MANIFEST_FILE
    ? (path.isAbsolute(process.env.V2_REVIEW_MANIFEST_FILE)
      ? process.env.V2_REVIEW_MANIFEST_FILE
      : path.resolve(ROOT_DIR, process.env.V2_REVIEW_MANIFEST_FILE))
    : path.join(V2_DB_DIR, 'review_tasks', 'review_task_manifest.review.v1.json'),
  V2_REVIEW_WRITE_ENABLED: resolveFlag('V2_REVIEW_WRITE_ENABLED'),
  V2_FIVE_STEP_AUDIT_WRITE_ENABLED: resolveFlag(
    'V2_FIVE_STEP_AUDIT_WRITE_ENABLED',
    V2_DB_PROFILE === 'local-test',
  ),
  DEEPSEEK_PARSE_API_KEY: process.env.DEEPSEEK_PARSE_API_KEY || process.env.DEEPSEEK_API_KEY || '',
  DEEPSEEK_ANALYSIS_API_KEY: process.env.DEEPSEEK_ANALYSIS_API_KEY || process.env.DEEPSEEK_API_KEY_BACKUP || process.env.DEEPSEEK_API_KEY || '',
  DEEPSEEK_MODEL: 'deepseek-v4-pro',
  DEEPSEEK_AUDIT_MODEL: process.env.DEEPSEEK_AUDIT_MODEL || 'deepseek-flash',
};

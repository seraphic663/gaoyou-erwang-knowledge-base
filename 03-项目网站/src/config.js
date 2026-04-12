const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.resolve(__dirname, '..');
const WORKSPACE_ROOT = path.resolve(ROOT_DIR, '..');
const PORT = Number(process.env.PORT || 3000);

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
  SQLITE_DB_FILE: path.join(WORKSPACE_ROOT, '02-数据库', 'data', 'dictionary.db'),
  SQLITE_BRIDGE_FILE: path.join(ROOT_DIR, 'scripts', 'sqlite_bridge.py'),
};

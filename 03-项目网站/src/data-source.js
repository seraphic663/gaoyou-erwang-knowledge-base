const { SnapshotSource } = require('./data-sources/snapshot-source');

function createDataSource(config) {
  if (config.SOURCE_MODE === 'sqlite') {
    try {
      const source = new SnapshotSource(config.SQLITE_SNAPSHOT_FILE, 'SQLite 实库快照');
      source.getHealth();
      return source;
    } catch (error) {
      if (String(process.env.DATA_SOURCE || '').trim().toLowerCase() === 'sqlite') {
        throw error;
      }
      const fallbackLabel = `Demo JSON（SQLite 快照不可用后回退：${error.message}）`;
      return new SnapshotSource(config.DEMO_DB_FILE, fallbackLabel, { createIfMissing: true });
    }
  }

  return new SnapshotSource(config.DEMO_DB_FILE, 'Demo JSON', { createIfMissing: true });
}

module.exports = { createDataSource };

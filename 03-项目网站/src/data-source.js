const { DemoJsonSource } = require('./data-sources/demo-json-source');
const { SQLiteSnapshotSource } = require('./data-sources/sqlite-bridge-source');

function createDataSource(config) {
  if (config.SOURCE_MODE === 'sqlite') {
    const sqliteSource = new SQLiteSnapshotSource(config);

    try {
      sqliteSource.getHealth();
      return sqliteSource;
    } catch (error) {
      if (String(process.env.DATA_SOURCE || '').trim().toLowerCase() === 'sqlite') {
        throw error;
      }

      const fallbackLabel = `Demo JSON（SQLite 快照不可用后回退：${error.message}）`;
      return new DemoJsonSource(config, { sourceLabel: fallbackLabel });
    }
  }

  return new DemoJsonSource(config);
}

module.exports = { createDataSource };

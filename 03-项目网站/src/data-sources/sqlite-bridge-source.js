const fs = require('fs');
const {
  buildCasePayload,
  buildSearch,
  buildBootstrap,
  buildContext,
  buildHealth,
  buildSchema,
  buildTermPayload,
  buildTermsPayload,
  searchCases,
} = require('./shared');

class SQLiteSnapshotSource {
  constructor(config) {
    this.snapshotFile = config.SQLITE_SNAPSHOT_FILE;
    this.dbFile = config.SQLITE_DB_FILE;
  }

  loadSnapshot() {
    if (!fs.existsSync(this.snapshotFile)) {
      throw new Error(`SQLite snapshot not found: ${this.snapshotFile}`);
    }

    try {
      const raw = fs.readFileSync(this.snapshotFile, 'utf8');
      const snapshot = JSON.parse(raw.replace(/^\uFEFF/, ''));
      snapshot.source = 'sqlite';
      snapshot.sourceLabel = snapshot.sourceLabel || 'SQLite 实库快照';
      return snapshot;
    } catch (error) {
      throw new Error(`Invalid SQLite snapshot: ${error.message}`);
    }
  }

  getHealth() {
    const context = buildContext(this.loadSnapshot());
    return buildHealth(context, {
      snapshotFile: this.snapshotFile,
      dbFile: this.dbFile,
      snapshotExists: fs.existsSync(this.snapshotFile),
      dbExists: fs.existsSync(this.dbFile),
      time: new Date().toISOString(),
    });
  }

  getBootstrap() {
    return buildBootstrap(buildContext(this.loadSnapshot()));
  }

  getSchema() {
    return buildSchema(buildContext(this.loadSnapshot()));
  }

  search(query) {
    return buildSearch(buildContext(this.loadSnapshot()), query);
  }

  searchCases(query) {
    return searchCases(buildContext(this.loadSnapshot()), query);
  }

  getTerm(termId) {
    return buildTermPayload(buildContext(this.loadSnapshot()), termId);
  }

  getCase(caseId) {
    return buildCasePayload(buildContext(this.loadSnapshot()), caseId);
  }

  getTerms() {
    return buildTermsPayload(buildContext(this.loadSnapshot()));
  }
}

module.exports = { SQLiteSnapshotSource };

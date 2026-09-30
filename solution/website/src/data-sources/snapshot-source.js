const fs = require('fs');
const path = require('path');
const {
  buildBrowserBootstrap,
  buildBrowserResult,
  buildCasePayload,
  buildSearch,
  buildBootstrap,
  buildContext,
  buildHealth,
  buildSchema,
  buildTermPayload,
  buildTermsPayload,
  parseJsonArray,
  searchCases,
} = require('./shared');

class SnapshotSource {
  constructor(snapshotFile, label, { createIfMissing = false } = {}) {
    this.snapshotFile = snapshotFile;
    this.label = label;
    this.createIfMissing = createIfMissing;
  }

  loadSnapshot() {
    if (!fs.existsSync(this.snapshotFile)) {
      if (this.createIfMissing) {
        const snapshot = this._emptySnapshot();
        fs.mkdirSync(path.dirname(this.snapshotFile), { recursive: true });
        fs.writeFileSync(this.snapshotFile, JSON.stringify(snapshot, null, 2), 'utf8');
        return snapshot;
      }
      throw new Error(`Snapshot not found: ${this.snapshotFile}`);
    }

    try {
      const raw = fs.readFileSync(this.snapshotFile, 'utf8');
      const snapshot = JSON.parse(raw.replace(/^﻿/, ''));
      snapshot.sourceLabel = this.label;
      return snapshot;
    } catch (error) {
      if (!this.createIfMissing) {
        throw new Error(`Invalid snapshot: ${error.message}`);
      }

      const brokenFile = `${this.snapshotFile}.broken.${Date.now()}`;
      if (fs.existsSync(this.snapshotFile)) {
        fs.copyFileSync(this.snapshotFile, brokenFile);
      }

      const snapshot = this._emptySnapshot();
      fs.writeFileSync(this.snapshotFile, JSON.stringify(snapshot, null, 2), 'utf8');
      return snapshot;
    }
  }

  _emptySnapshot() {
    return {
      schemaVersion: 3,
      source: 'demo',
      sourceLabel: this.label,
      tables: {
        works: [],
        passages: [],
        terms: [],
        cases: [],
        evidences: [],
      },
    };
  }

  getHealth() {
    const context = buildContext(this.loadSnapshot());
    return buildHealth(context, {
      snapshotFile: this.snapshotFile,
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

  getBrowserBootstrap() {
    return buildBrowserBootstrap(buildContext(this.loadSnapshot()));
  }

  browse(options) {
    return buildBrowserResult(buildContext(this.loadSnapshot()), options);
  }

  getTerms() {
    return buildTermsPayload(buildContext(this.loadSnapshot()));
  }
}

module.exports = { SnapshotSource };

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

function createEmptySnapshot() {
  return {
    schemaVersion: 3,
    source: 'demo',
    sourceLabel: 'Demo JSON',
    tables: {
      works: [],
      passages: [],
      terms: [],
      cases: [],
      evidences: [],
    },
  };
}

function normalizeDemoSnapshot(rawDb) {
  const tables = rawDb?.tables || {};

  return {
    schemaVersion: 3,
    source: 'demo',
    sourceLabel: 'Demo JSON',
    tables: {
      works: (tables.works || []).map((item) => ({
        id: item.id,
        title: item.title,
        author: item.author,
        work_type: item.workType,
        dynasty: item.dynasty,
        time_note: item.timeNote,
        notes: item.notes,
      })),
      passages: (tables.passages || []).map((item) => ({
        id: item.id,
        work_id: item.workId,
        juan: item.juan,
        chapter: item.chapter,
        location_note: item.locationNote,
        raw_text: item.rawText,
        normalized_text: item.normalizedText,
        passage_type: item.passageType,
      })),
      terms: (tables.terms || []).map((item) => ({
        id: item.id,
        term: item.term,
        term_type: item.termType,
        category: item.category,
        aliases: JSON.stringify(Array.isArray(item.aliases) ? item.aliases : []),
        notes: item.notes || '',
        core_meaning: item.coreMeaning || '',
        case_ids: JSON.stringify([]),
      })),
      cases: (tables.cases || []).map((item) => ({
        id: item.id,
        title: item.title,
        section_title: item.sectionTitle || '',
        volume_title: item.volumeTitle || '',
        term_ids: JSON.stringify(
          item.termIds
            ? parseJsonArray(item.termIds)
            : item.termId
              ? [item.termId]
              : [],
        ),
        erwang_passage_id: item.erwangPassageId || null,
        target_passage_id: item.targetPassageId || null,
        problem: item.problem || '',
        method: item.method || '',
        process_text: item.processText || '',
        conclusion: item.conclusion || '',
        certainty: item.certainty || '',
        status: item.status || '',
      })),
      evidences: (tables.evidences || []).map((item) => ({
        id: item.id,
        case_id: item.caseId,
        term_id: item.termId || null,
        source_passage_id: item.sourcePassageId || null,
        work_id: item.workId || null,
        evidence_type: item.evidenceType || '',
        quote_text: item.quoteText || '',
        core_snippet: item.coreSnippet || '',
        note: item.note || '',
      })),
    },
  };
}

class DemoJsonSource {
  constructor(config, options = {}) {
    this.dbFile = config.DEMO_DB_FILE;
    this.label = options.sourceLabel || 'Demo JSON';
  }

  ensureDatabaseFile() {
    fs.mkdirSync(path.dirname(this.dbFile), { recursive: true });
    if (!fs.existsSync(this.dbFile)) {
      fs.writeFileSync(this.dbFile, JSON.stringify(createEmptySnapshot(), null, 2), 'utf8');
    }
  }

  loadSnapshot() {
    this.ensureDatabaseFile();

    try {
      const raw = fs.readFileSync(this.dbFile, 'utf8');
      const parsed = JSON.parse(raw.replace(/^\uFEFF/, ''));
      const snapshot = normalizeDemoSnapshot(parsed);
      snapshot.sourceLabel = this.label;
      return snapshot;
    } catch {
      const brokenFile = `${this.dbFile}.broken.${Date.now()}`;
      if (fs.existsSync(this.dbFile)) {
        fs.copyFileSync(this.dbFile, brokenFile);
      }

      const snapshot = createEmptySnapshot();
      snapshot.sourceLabel = this.label;
      fs.writeFileSync(this.dbFile, JSON.stringify(snapshot, null, 2), 'utf8');
      return snapshot;
    }
  }

  getHealth() {
    const context = buildContext(this.loadSnapshot());
    return buildHealth(context, {
      dbFile: this.dbFile,
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

module.exports = { DemoJsonSource };

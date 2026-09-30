const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  buildAnnotationSearchIndex,
  buildAnnotationBootstrap,
  browseAnnotations,
  deriveAnnotator,
  getAnnotationCase,
  normalizeOrigin,
} = require('../src/annotation-browser');

function withSnapshot(snapshot) {
  const file = path.join(os.tmpdir(), `annotation-browser-${process.pid}.json`);
  fs.writeFileSync(file, JSON.stringify(snapshot), 'utf8');
  return {
    file,
    config: { ANNOTATION_SNAPSHOT_FILE: file },
  };
}

test('derives annotator from the last filename segment and normalizes book marks', () => {
  assert.equal(deriveAnnotator('读书杂志_平原之隰-譕臣_卢飞宇.docx'), '卢飞宇');
  assert.equal(deriveAnnotator('004-经传释词-诸书-允-徐健怡.md'), '徐健怡');
  assert.equal(normalizeOrigin('《经传释词》'), '经传释词');
});

test('builds and applies annotator and origin filters', () => {
  const snapshot = {
    counts: { documents: 2, cases: 3, terms: 0, evidences: 0, processSteps: 0 },
    documentCounts: {},
    methodCounts: {},
    cases: [
      {
        id: 1,
        case_title: '甲',
        source_work: '《经传释词》',
        source_document: { source_file_name: '经传释词第二-甲_李汶灿.docx' },
        target_text: '经传释词正文',
        method_tags: [],
      },
      {
        id: 2,
        case_title: '乙',
        source_work: '经传释词',
        source_document: { source_file_name: '004-经传释词-乙-徐健怡.md' },
        target_text: '经传释词另一条正文',
        method_tags: [],
      },
      {
        id: 3,
        case_title: '丙',
        source_work: '读书杂志',
        source_document: { source_file_name: '读书杂志-丙-李汶灿.md' },
        method_tags: [],
      },
    ],
  };
  const { file, config } = withSnapshot(snapshot);
  try {
    const bootstrap = buildAnnotationBootstrap(config);
    const searchIndex = buildAnnotationSearchIndex(config);
    assert.equal(searchIndex.items.length, 3);
    assert.equal(searchIndex.items[0].evidences, undefined);
    assert.match(searchIndex.items[0].search_text, /甲/);
    assert.equal(getAnnotationCase(config, 1).case_title, '甲');
    assert.deepEqual(
      bootstrap.annotators.map((item) => [item.value, item.count]),
      [['all', 3], ['徐健怡', 1], ['李汶灿', 2]],
    );
    assert.deepEqual(
      bootstrap.origins.map((item) => [item.value, item.count]),
      [['all', 3], ['经传释词', 2], ['读书杂志', 1]],
    );

    const byAnnotator = browseAnnotations(config, { annotator: '徐健怡' });
    assert.equal(byAnnotator.total, 1);
    assert.equal(byAnnotator.items[0].origin, '经传释词');

    const byOrigin = browseAnnotations(config, { origin: '经传释词' });
    assert.equal(byOrigin.total, 2);
    assert.deepEqual(byOrigin.items.map((item) => item.annotator), ['李汶灿', '徐健怡']);

    const byMultiFilter = browseAnnotations(config, {
      annotators: ['李汶灿', '徐健怡'],
      origins: ['经传释词', '读书杂志'],
    });
    assert.equal(byMultiFilter.total, 3);

    const byTraditionalQuery = browseAnnotations(config, { query: '經傳釋詞' });
    assert.equal(byTraditionalQuery.total, 2);

    const byContentQuery = browseAnnotations(config, { query: '甲文' });
    assert.equal(byContentQuery.total, 0);

    const metadataOnlyQuery = browseAnnotations(config, { query: '徐健怡' });
    assert.equal(metadataOnlyQuery.total, 0);
  } finally {
    fs.rmSync(file, { force: true });
  }
});

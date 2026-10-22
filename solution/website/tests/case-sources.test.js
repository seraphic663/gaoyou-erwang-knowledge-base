const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const CaseSources = require('../web/assets/js/case-sources');
const { SnapshotSource } = require('../src/data-sources/snapshot-source');

const readerScript = fs.readFileSync(path.join(__dirname, '../web/assets/js/case-reader.js'), 'utf8');
const escape = value => String(value ?? '').replace(/[&<>"']/g, character =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);

async function render(source, payload) {
  const elements = { '#caseReader': {}, '#detailTitle': {}, '#caseAudit': {} };
  const context = {
    URLSearchParams,
    location: { search: '?source=' + source + '&id=1' },
    document: { querySelector: selector => elements[selector] },
    CaseSources,
    escapeHtml: escape,
    requestJson: async () => payload,
    Site: {
      url: (pathname, query) => pathname + '?' + new URLSearchParams(query),
      current: () => '/case?source=' + source + '&id=1',
      link: (href, label) => '<a href="' + escape(href) + '">' + escape(label) + '</a>',
      caseUrl: (origin, id) => '/case?source=' + origin + '&id=' + id,
      auditLinks: async () => ({ 1: [] }),
      auditMarkup: () => '',
    },
  };
  await vm.runInNewContext(readerScript, context);
  // A raw JSON escape hatch must never mask an empty reader.
  return elements['#caseReader'].innerHTML.replace(/<details[\s\S]*?<\/details>/g, '');
}

test('real main evidence quoteText appears in the readable view, not only raw JSON', async () => {
  const source = new SnapshotSource(path.join(__dirname, '../data/sqlite-snapshot.json'), 'test');
  const payload = source.getCase(1);
  assert.ok(payload.evidences[0].quoteText);
  const model = CaseSources.detail('main', payload);
  assert.equal(model.evidence[0].quote, payload.evidences[0].quoteText);
  const html = await render('main', payload);
  assert.ok(html.includes(escape(payload.evidences[0].quoteText)));
  assert.equal(payload.evidences[0].quoteText, model.raw.evidences[0].quoteText);
});

test('annotation claim and conclusion remain independent and text is escaped', async () => {
  const payload = { ok: true, item: {
    id: 1, case_title: '人工标注', problem: 'PROBLEM', claim: 'CLAIM',
    conclusion: 'CONCLUSION', target_text: 'TARGET',
    terms: [{ term: '原字', related_term: '改字', relation_type: '校勘' }],
    evidences: [{ quote: '<script>not code</script>', work: '典籍' }],
  } };
  const before = JSON.stringify(payload);
  const model = CaseSources.detail('annotation', payload);
  assert.equal(model.terms[0].label, '原字 → 改字');
  const html = await render('annotation', payload);
  for (const field of ['PROBLEM', 'CLAIM', 'CONCLUSION', 'TARGET']) assert.ok(html.includes(field), field);
  assert.ok(html.includes('&lt;script&gt;not code&lt;/script&gt;'));
  assert.equal(JSON.stringify(payload), before);
});

test('V2 content uses its explicit field contract and preserves opaque case IDs', () => {
  const payload = {
    case_id: 'candidate-shell:原/文?x', case_title: 'V2',
    case_data: { problem_discovery: '发疑内容', research_question: '设问内容', conclusion: '结论内容' },
    source_passage: { passage_id: 'p:1', raw_text: '来源原文' },
    terms: [{ source_term: '甲', target_term: '乙', relation_type: '通假' }],
    process_steps: [{ field_name: 'reasoning', step_text: '释理内容' }],
  };
  const model = CaseSources.detail('v2', payload);
  assert.equal(model.id, payload.case_id);
  assert.equal(model.problem, '发疑内容');
  assert.equal(model.claim, '设问内容');
  assert.equal(model.steps[0].label, '释理');
  assert.equal(model.passages[0].text, '来源原文');
  assert.equal(new URL(CaseSources.detailUrl('v2', model.id), 'http://local').searchParams.get('id'), model.id);
});

test('list queries preserve source-specific repeated filters without mixing ID namespaces', () => {
  const params = new URLSearchParams('q=校勘&page_annotation=3&annotator=甲&annotator=乙&machine_status=draft');
  const annotation = new URL(CaseSources.listUrl('annotation', params), 'http://local');
  assert.deepEqual(annotation.searchParams.getAll('annotator'), ['甲', '乙']);
  assert.equal(annotation.searchParams.get('page'), '3');
  assert.equal(annotation.searchParams.has('machine_status'), false);
  assert.equal(CaseSources.summary('annotation', { id: 1 }).source, 'annotation');
  assert.throws(() => CaseSources.detailUrl('toString', 1), /未知/);
});

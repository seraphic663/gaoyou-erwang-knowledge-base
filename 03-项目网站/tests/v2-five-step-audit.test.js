const test = require('node:test');
const assert = require('node:assert/strict');
const { buildV2AuditContext, fingerprintV2Case, normalizeDraft, STEPS } = require('../src/v2-five-step-audit');

function sampleCase() {
  return {
    case_id: 'case-1',
    case_title: '测试案例',
    origin: 'unit-test',
    machine_status: 'draft',
    human_status: 'pending',
    source_work: '经义述闻',
    target_work: '左传',
    target_text: '造舟于河',
    source_passage_id: 'passage-1',
    case_data: { conclusion: 'draft conclusion' },
    provenance: { source_file: 'source.md', source_format: 'markdown' },
    source_passage: { passage_id: 'passage-1', raw_text: '造舟于河。', canonical_status: 'canonical_active' },
    evidences: [{
      evidence_index: 1,
      quote: '造舟为梁',
      quote_check: 'unchecked',
      source_work: '诗经',
      data: { source_resolution: 'legacy_derived_passage' },
      source_passage: { passage_id: 'passage-2', raw_text: '造舟为梁。', canonical_status: 'unknown' },
    }],
    process_steps: [{ field_name: 'reasoning', step_text: 'machine reasoning' }],
  };
}

test('normalizes all five steps in canonical order and validates evidence references', () => {
  const reversed = [...STEPS].reverse().map(({ field }) => ({
    field,
    text: field,
    evidence_refs: field === 'reasoning' ? [1] : [],
    review_questions: [],
  }));
  const draft = normalizeDraft({ steps: reversed }, new Set([1]));
  assert.deepEqual(draft.map((step) => step.field), STEPS.map((step) => step.field));
  assert.deepEqual(draft.find((step) => step.field === 'reasoning').evidence_refs, [1]);
  assert.throws(() => normalizeDraft({ steps: reversed }, new Set([])), /invalid_evidence_ref/);
});

test('builds only the selected V2 case context and keeps source uncertainty visible', () => {
  const context = buildV2AuditContext(sampleCase());
  assert.equal(context.record.case_id, 'case-1');
  assert.equal(context.evidences[0].source_resolution, 'legacy_derived_passage');
  assert.equal(context.evidences[0].quote_check, 'unchecked');
  assert.equal(context.evidences[0].source_passage.canonical_status, 'unknown');
  assert.equal(context.evidences.length, 1);
});

test('fingerprint changes when source text or evidence changes', () => {
  const item = sampleCase();
  const original = fingerprintV2Case(item);
  item.source_passage.raw_text = '改动后的段落';
  assert.notEqual(fingerprintV2Case(item), original);
});

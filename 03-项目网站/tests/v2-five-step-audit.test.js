const test = require('node:test');
const assert = require('node:assert/strict');
const {
  buildV2AuditContext,
  buildUserPrompt,
  fingerprintV2Case,
  generateFiveStepDraft,
  normalizeDraft,
  OUTPUT_TOKEN_BUDGETS,
  PROMPT_LIMITS,
  STEPS,
} = require('../src/v2-five-step-audit');

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

test('sends readable material cards to the model instead of database status fields', () => {
  const prompt = buildUserPrompt(buildV2AuditContext(sampleCase()));
  assert.match(prompt, /引文还没有核对原典/);
  assert.match(prompt, /来自旧材料整理/);
  assert.doesNotMatch(prompt, /quote_check|source_resolution|evidence_index/);
});

test('bounds long prompt fields and marks the omitted portions', () => {
  const item = sampleCase();
  item.target_text = '目'.repeat(PROMPT_LIMITS.targetTextChars + 20);
  item.source_passage.raw_text = '原'.repeat(PROMPT_LIMITS.primaryPassageChars + 20);
  item.process_steps = [{
    field_name: 'reasoning',
    step_text: '理'.repeat(PROMPT_LIMITS.processStepChars + 20),
  }];
  item.terms = [{ relation_note: '词'.repeat(PROMPT_LIMITS.termNoteChars + 20) }];
  item.evidences[0].quote = '引'.repeat(PROMPT_LIMITS.evidenceQuoteChars + 20);
  item.evidences[0].data.evidence_note = '注'.repeat(PROMPT_LIMITS.evidenceNoteChars + 20);

  const context = buildV2AuditContext(item);
  assert.equal(context.source_passage.text.length, PROMPT_LIMITS.primaryPassageChars);
  assert.equal(context.source_passage.text_truncated, true);
  assert.equal(context.record.target_text.length, PROMPT_LIMITS.targetTextChars);
  assert.equal(context.record.target_text_truncated, true);
  assert.equal(context.record.existing_five_steps.reasoning.length, PROMPT_LIMITS.processStepChars);
  assert.equal(context.record.existing_five_steps_truncated.reasoning, true);
  assert.equal(context.record.terms[0].relation_note.length, PROMPT_LIMITS.termNoteChars);
  assert.equal(context.record.terms[0].relation_note_truncated, true);
  assert.equal(context.evidences[0].quote.length, PROMPT_LIMITS.evidenceQuoteChars);
  assert.equal(context.evidences[0].quote_truncated, true);
  assert.equal(context.evidences[0].evidence_note.length, PROMPT_LIMITS.evidenceNoteChars);
  assert.equal(context.evidences[0].evidence_note_truncated, true);
});

test('allocates a larger output budget for thinking effort', () => {
  assert.equal(OUTPUT_TOKEN_BUDGETS.none, 16384);
  assert.equal(OUTPUT_TOKEN_BUDGETS.low, 24576);
  assert.equal(OUTPUT_TOKEN_BUDGETS.high, 32768);
  assert.equal(OUTPUT_TOKEN_BUDGETS.max, 65536);
});

test('fingerprint changes when source text or evidence changes', () => {
  const item = sampleCase();
  const original = fingerprintV2Case(item);
  item.source_passage.raw_text = '改动后的段落';
  assert.notEqual(fingerprintV2Case(item), original);
});

test('returns an actionable response when the DeepSeek audit key is missing', async () => {
  const result = await generateFiveStepDraft(
    { DEEPSEEK_ANALYSIS_API_KEY: '' },
    { case_id: 'case-1', model: 'deepseek-flash', reasoning_effort: 'high' },
  );
  assert.equal(result.status, 503);
  assert.match(result.payload.message, /API key is not configured/);
});

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { generate, retrieve, checkCitations, buildQueryVariants } = require('../src/reading-harness');

const baseConfig = {
  DEEPSEEK_ANALYSIS_API_KEY: 'test-only-key',
  READING_HARNESS_MODEL: 'deepseek-flash',
};

function modelReply(result) {
  return {
    ok: true,
    json: async () => ({
      model: 'deepseek-flash',
      usage: { total_tokens: 42 },
      choices: [{ finish_reason: 'stop', message: { content: JSON.stringify(result) } }],
    }),
  };
}

function collationResult(overrides = {}) {
  return {
    steps: [
      'problem_discovery', 'research_question', 'evidence_collection', 'reasoning', 'conclusion',
    ].map((field) => ({ field, text: '原字可通，暂未见需校改的疑点。', citation_indexes: [] })),
    conclusion_type: 'keep_text',
    proposed_reading: '',
    uncertainties: '',
    citations: [],
    ...overrides,
  };
}

test('v1 sends only original and question; it never invokes corpus bridge', async () => {
  let sent;
  const outcome = await generate({
    ...baseConfig,
    READING_HARNESS_BRIDGE_FILE: 'missing-bridge-must-not-run.py',
    READING_HARNESS_DB_FILE: 'missing-db-must-not-open.sqlite3',
  }, {
    mode: 'v1',
    original_text: '原文说无须改字。',
    question: '需要改字吗？',
    case_id: 'must-not-use',
    gold: 'must-not-use',
  }, async (_url, options) => {
    sent = JSON.parse(options.body);
    return modelReply(collationResult({
      citations: [{ evidence_id: 'ORIGINAL', quote: '无须改字', claim: '原字可通', relation: 'supports' }],
    }));
  });
  assert.equal(outcome.status, 200);
  assert.deepEqual(Object.keys(JSON.parse(sent.messages[1].content)), ['original_text', 'question']);
  assert.equal(sent.model, 'deepseek-flash');
  assert.equal(sent.reasoning_effort, 'high');
  assert.equal(sent.max_tokens, 32768);
  assert.deepEqual(outcome.payload.evidence, []);
  assert.equal(outcome.payload.citation_checks[0].valid, true);
  assert.equal(outcome.payload.prompt_version, 'reading-harness.collation.v5');
  assert.match(sent.messages[0].content, /uncertainties（集中未决问题与后续思考的字符串/);
  assert.match(sent.messages[0].content, /可选 rationale（若提供必须为字符串）/);
  assert.match(sent.messages[0].content, /五步各写增量信息/);
  assert.match(sent.messages[0].content, /前五步正文不要重复列未决问题、后续提醒/);
  assert.match(sent.messages[0].content, /uncertainties 供辅助第六页展示，不要增添第六个 step/);
  assert.match(sent.messages[0].content, /一个判断涉及两条证据时写 \[C1\]\[C2\]/);
  assert.equal(outcome.payload.result.steps.length, 5);
  assert.equal(outcome.payload.result.conclusion_type, 'keep_text');
});

test('self-reported source is carried unchanged in v1 without accepting gold fields', async () => {
  let sent;
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原字可通。', question: '是否需校改？',
    source_work: '自报《甲书》', source_location: '卷二·某章', gold: '不可发送',
  }, async (_url, options) => {
    sent = JSON.parse(options.body);
    return modelReply(collationResult());
  });
  assert.equal(outcome.status, 200);
  const user = JSON.parse(sent.messages[1].content);
  assert.deepEqual(Object.keys(user), ['original_text', 'question', 'source_work', 'source_location']);
  assert.equal(user.source_work, '自报《甲书》');
  assert.equal(user.source_location, '卷二·某章');
  assert.doesNotMatch(JSON.stringify(sent), /不可发送/);
  assert.equal(outcome.payload.result.steps[0].field, 'problem_discovery');
  assert.match(outcome.payload.result.steps[0].text, /未见需校改的疑点/);
});

test('v2 rebuilds server evidence from external bridge and checks the quote', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'reading-harness-'));
  const bridge = path.join(tmp, 'bridge.py');
  fs.writeFileSync(bridge, [
    'import json, sys',
    'assert sys.argv[1] == "retrieve"',
    'payload = json.load(sys.stdin)',
    'assert set(payload) == {"original_text", "question", "query_variants", "limit", "max_chars"}',
    'assert payload["limit"] == 6 and payload["max_chars"] == 6000',
    'assert payload["query_variants"]["original_text"][0] == payload["original_text"]',
    'assert payload["query_variants"]["question"][0] == payload["question"]',
    'item = {"evidence_id":"R1","evidence_text":"邻段：甲书明言不改字。","chunk_id":"E1","source_id":"S1","source_title":"外典甲","full_text":"甲书明言不改字。","line_start":2,"line_end":2}',
    'print(json.dumps({"ok":True,"data":{"items":[item],"context":"[R1] 外典甲\\n邻段：甲书明言不改字。","hit_count":1}}, ensure_ascii=False))',
  ].join('\n'), 'utf8');
  try {
    let sent;
    const outcome = await generate({
      ...baseConfig,
      PYTHON_BIN: process.env.V2_PYTHON_BIN || 'python',
      ROOT_DIR: tmp,
      READING_HARNESS_BRIDGE_FILE: bridge,
      READING_HARNESS_DB_FILE: path.join(tmp, 'unused.sqlite3'),
    }, {
      mode: 'v2', original_text: '學問原文乙。', question: '如何判断？',
      source_work: '用户自报甲书', source_location: '卷一·第一章',
      evidence: [{ chunk_id: 'FORGED', full_text: '伪造答案' }], gold: '不得进入模型',
    }, async (_url, options) => {
      sent = JSON.parse(options.body);
      return modelReply(collationResult({
        citations: [{ evidence_id: 'R1', quote: '邻段：', claim: '邻段可定位', relation: 'background' }],
      }));
    });
    assert.equal(outcome.status, 200);
    const user = JSON.parse(sent.messages[1].content);
    assert.deepEqual(Object.keys(user), ['original_text', 'question', 'source_work', 'source_location', 'external_evidence']);
    assert.equal(user.original_text, '學問原文乙。');
    assert.equal(user.source_work, '用户自报甲书');
    assert.equal(user.source_location, '卷一·第一章');
    assert.equal(outcome.payload.retrieval.user_supplied_source.source_work, '用户自报甲书');
    assert.equal(outcome.payload.retrieval.query_variants.original_text[0], '學問原文乙。');
    assert.ok(outcome.payload.retrieval.query_variants.original_text.some((text) => text.includes('学问')));
    assert.match(user.external_evidence, /甲书明言不改字/);
    assert.doesNotMatch(JSON.stringify(sent), /FORGED|伪造答案|不得进入模型/);
    assert.equal(outcome.payload.evidence[0].chunk_id, 'E1');
    assert.equal(outcome.payload.evidence[0].evidence_id, 'R1');
    assert.equal(outcome.payload.citation_checks[0].valid, true);
    assert.equal(outcome.payload.citation_checks[0].match_field, 'evidence_text');
    assert.equal(outcome.payload.citation_status, 'all_quotes_located');
    assert.equal(sent.messages[0].content, require('../src/reading-harness').SYSTEM_PROMPT);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('unknown and absent quotes are reported without rewriting the result', async () => {
  const outcome = await generate({
    ...baseConfig,
    READING_HARNESS_BRIDGE_FILE: 'missing-bridge-must-not-run.py',
  }, { mode: 'v1', original_text: '原文未决。', question: '判断？' }, async () => modelReply(collationResult({
    conclusion_type: 'insufficient_evidence', uncertainties: '证据不足。',
    citations: [
      { evidence_id: 'R1', quote: '未决', claim: '错误来源', relation: 'supports' },
      { evidence_id: 'ORIGINAL', quote: '不存在的文字', claim: '错误引文', relation: 'contradicts' },
    ],
  })));
  assert.equal(outcome.status, 200);
  assert.equal(outcome.payload.citation_status, 'unlocated_quote_or_id');
  assert.equal(outcome.payload.citations_all_valid, false);
  assert.equal(outcome.payload.citation_checks[0].valid_id, false);
  assert.equal(outcome.payload.citation_checks[1].valid_quote, false);
  assert.equal(outcome.payload.result.citations.length, 2);
});

test('five-step citation indexes are zero-based and schema errors retain raw output', async () => {
  const citation = { evidence_id: 'ORIGINAL', quote: '原文', claim: '原字可通', relation: 'supports' };
  const valid = collationResult({ citations: [citation] });
  valid.steps[2].citation_indexes = [0];
  const input = { mode: 'v1', original_text: '原文可通。', question: '是否需校改？' };
  const good = await generate(baseConfig, input, async () => modelReply(valid));
  assert.equal(good.status, 200);
  assert.deepEqual(good.payload.result.steps[2].citation_indexes, [0]);

  const invalid = collationResult({ citations: [citation] });
  invalid.steps[2].citation_indexes = [1];
  const bad = await generate(baseConfig, input, async () => modelReply(invalid));
  assert.equal(bad.status, 200, bad.payload.message);
  assert.deepEqual(bad.payload.result.steps[2].citation_indexes, [0]);
  assert.deepEqual(bad.payload.result.steps[2].citation_ids, ['C1']);
  assert.equal(bad.payload.result.citations[0].citation_id, 'C1');
  assert.equal(bad.payload.provider_output.content, JSON.stringify(invalid));
});

test('explicit citation IDs and field labels recover shuffled steps without losing legacy indexes', async () => {
  const result = collationResult({
    citations: [{
      citation_id: 'C-prose-1', evidence_id: 'ORIGINAL', quote: '原字',
      claim: '原字可以保留', rationale: '句法与上下文相合', relation: 'supports',
    }],
    steps: [
      { field: 'conclusion', text: '倾向保留原字，因为上下文能通。', citation_ids: ['C-prose-1'] },
      { field: 'problem_discovery', text: '要判断原字能否成立。', citation_ids: ['C-prose-1'] },
      { field: 'reasoning', text: '上下文支持保留。', citation_ids: ['C-prose-1'] },
      { field: 'evidence_collection', text: '材料支持原字可通。', citation_ids: ['C-prose-1'] },
      { field: 'research_question', text: '是否需要改字？', citation_ids: ['C-prose-1'] },
    ],
  });
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原字可通。', question: '是否需要改字？',
  }, async () => modelReply(result));

  assert.equal(outcome.status, 200, outcome.payload.message);
  assert.deepEqual(outcome.payload.result.steps.map((step) => step.field), [
    'problem_discovery', 'research_question', 'evidence_collection', 'reasoning', 'conclusion',
  ]);
  assert.deepEqual(outcome.payload.result.steps[4].citation_ids, ['C-prose-1']);
  assert.deepEqual(outcome.payload.result.steps[4].citation_indexes, [0]);
  assert.equal(outcome.payload.result.citations[0].citation_id, 'C-prose-1');
  assert.equal(outcome.payload.result.citations[0].rationale, '句法与上下文相合');
  assert.equal(outcome.payload.citation_checks[0].citation_id, 'C-prose-1');
});

test('generated citation IDs avoid collisions with provider IDs', async () => {
  const result = collationResult({ citations: [
    { citation_id: 'C2', evidence_id: 'ORIGINAL', quote: '原字', claim: '判断甲', relation: 'supports' },
    { evidence_id: 'ORIGINAL', quote: '可通', claim: '判断乙', relation: 'neutral' },
  ] });
  result.steps[4].citation_indexes = [1];
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原字可通。', question: '如何判断？',
  }, async () => modelReply(result));

  assert.equal(outcome.status, 200, outcome.payload.message);
  assert.deepEqual(outcome.payload.result.citations.map((citation) => citation.citation_id), ['C2', 'C1']);
  assert.deepEqual(outcome.payload.result.steps[4].citation_ids, ['C1']);
});

test('body citation markers join their step references without renumbering cards', async () => {
  const result = collationResult({ citations: [
    { citation_id: 'C2', evidence_id: 'ORIGINAL', quote: '原字', claim: '保留原字', relation: 'supports' },
    { citation_id: 'C1', evidence_id: 'ORIGINAL', quote: '可通', claim: '句义可通', relation: 'supports' },
  ] });
  delete result.steps[3].citation_indexes;
  result.steps[3].citation_ids = ['C2'];
  result.steps[3].text = '原字可保留[C2]，句义也可通[C1]。';
  delete result.steps[4].citation_indexes;
  result.steps[4].citation_ids = [];
  result.steps[4].text = '倾向保留原字[C2, C1]。';
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原字可通。', question: '是否应校改？',
  }, async () => modelReply(result));

  assert.equal(outcome.status, 200, outcome.payload.message);
  assert.deepEqual(outcome.payload.result.citations.map(({ citation_id }) => citation_id), ['C2', 'C1']);
  assert.deepEqual(outcome.payload.result.steps[3].citation_ids, ['C2', 'C1']);
  assert.deepEqual(outcome.payload.result.steps[3].citation_indexes, [0, 1]);
  assert.deepEqual(outcome.payload.result.steps[4].citation_ids, ['C2', 'C1']);
  assert.equal(outcome.payload.provider_output.content, JSON.stringify(result));
  assert.deepEqual(outcome.payload.result.steps[0].citation_ids, []);
});

test('bare citation IDs and Chinese range wording resolve to the same cards', async () => {
  const result = collationResult({ citations: [1, 2, 3, 4, 5].map((number) => ({
    citation_id: `C${number}`, evidence_id: 'ORIGINAL', quote: '原字',
    claim: `判断${number}`, relation: 'supports',
  })) });
  delete result.steps[2].citation_indexes;
  result.steps[2].citation_ids = ['C4'];
  result.steps[2].text = 'C1为基础文本；C2作旁证；C3至C5可比较，ABC1与C2x不是引用。';
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原字可通。', question: '如何判断？',
  }, async () => modelReply(result));

  assert.equal(outcome.status, 200, outcome.payload.message);
  assert.deepEqual(outcome.payload.result.steps[2].citation_ids, ['C4', 'C1', 'C2', 'C3', 'C5']);
  assert.deepEqual(outcome.payload.result.steps[2].citation_indexes, [3, 0, 1, 2, 4]);
  assert.equal(outcome.payload.provider_output.content, JSON.stringify(result));
  assert.equal(outcome.payload.prompt_version, 'reading-harness.collation.v5');
});

test('unknown body citation marker fails with raw provider output and no retry', async () => {
  const result = collationResult({ citations: [
    { citation_id: 'C1', evidence_id: 'ORIGINAL', quote: '原字', claim: '原字可通', relation: 'supports' },
  ] });
  result.steps[3].text = '材料支持保留[C9]。';
  let calls = 0;
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原字可通。', question: '如何判断？',
  }, async () => { calls += 1; return modelReply(result); });

  assert.equal(outcome.status, 502);
  assert.equal(calls, 1);
  assert.match(outcome.payload.message, /step_text_unknown_citation_id:C9/);
  assert.equal(outcome.payload.provider_output.content, JSON.stringify(result));
  assert.equal(outcome.payload.format_repair, null);
});

test('unknown bare citation ID fails with raw provider output and no retry', async () => {
  const result = collationResult({ citations: [
    { citation_id: 'C1', evidence_id: 'ORIGINAL', quote: '原字', claim: '原字可通', relation: 'supports' },
  ] });
  result.steps[3].text = '现有材料参见 C99，尚待核对。';
  let calls = 0;
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原字可通。', question: '如何判断？',
  }, async () => { calls += 1; return modelReply(result); });

  assert.equal(outcome.status, 502);
  assert.equal(calls, 1);
  assert.match(outcome.payload.message, /step_text_unknown_citation_id:C99/);
  assert.equal(outcome.payload.provider_output.content, JSON.stringify(result));
  assert.equal(outcome.payload.format_repair, null);
});

test('neutral relation is accepted and ambiguous legacy indexes remain zero-based', async () => {
  const result = collationResult({
    citations: [
      { evidence_id: 'ORIGINAL', quote: '原字', claim: '可保留', relation: 'supports' },
      { evidence_id: 'ORIGINAL', quote: '可通', claim: '背景参照', relation: 'neutral', rationale: '只说明语境' },
    ],
  });
  result.steps[4].citation_indexes = [1];
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原字可通。', question: '如何判断？',
  }, async () => modelReply(result));

  assert.equal(outcome.status, 200, outcome.payload.message);
  assert.deepEqual(outcome.payload.result.steps[4].citation_indexes, [1]);
  assert.deepEqual(outcome.payload.result.steps[4].citation_ids, ['C2']);
  assert.equal(outcome.payload.result.citations[1].relation, 'neutral');
  assert.equal(outcome.payload.result.citations[1].rationale, '只说明语境');
});

test('unparseable JSON keeps the original response and usage without a paid repair call', async () => {
  const result = collationResult();
  const originalContent = JSON.stringify(result).slice(0, -1);
  let calls = 0;
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原文可通。', question: '是否需要校改？',
  }, async () => {
    calls += 1;
    return calls === 1
      ? {
        ok: true,
        json: async () => ({
          model: 'deepseek-flash',
          usage: { total_tokens: 42 },
          choices: [{ finish_reason: 'stop', message: { content: originalContent } }],
        }),
      }
      : modelReply(result);
  });

  assert.equal(outcome.status, 502);
  assert.equal(calls, 1);
  assert.equal(outcome.payload.provider_output.content, originalContent);
  assert.equal(outcome.payload.provider_output.usage.total_tokens, 42);
  assert.equal(outcome.payload.format_repair, null);
  assert.equal(outcome.payload.trace.request_body.messages[1].content, JSON.stringify({
    original_text: '原文可通。', question: '是否需要校改？',
  }));
});

test('one surrounding JSON code fence is stripped without changing provider output', async () => {
  const raw = `\n\`\`\`json\n${JSON.stringify(collationResult())}\n\`\`\`\n`;
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原文。', question: '如何读？',
  }, async () => ({
    ok: true,
    json: async () => ({ choices: [{ finish_reason: 'stop', message: { content: raw } }] }),
  }));

  assert.equal(outcome.status, 200, outcome.payload.message);
  assert.equal(outcome.payload.provider_output.content, raw);
  assert.equal(outcome.payload.format_repair, null);
});

test('a sole result wrapper is unwrapped deterministically with one provider call', async () => {
  const wrapped = { result: collationResult() };
  let calls = 0;
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原文。', question: '如何读？',
  }, async () => { calls += 1; return modelReply(wrapped); });

  assert.equal(outcome.status, 200, outcome.payload.message);
  assert.equal(calls, 1);
  assert.deepEqual(outcome.payload.result.steps.map((step) => step.field), [
    'problem_discovery', 'research_question', 'evidence_collection', 'reasoning', 'conclusion',
  ]);
  assert.equal(outcome.payload.provider_output.content, JSON.stringify(wrapped));
  assert.equal(outcome.payload.format_repair, null);
});

test('an unresolved citation ID fails once without changing its association', async () => {
  const result = collationResult({ citations: [
    { citation_id: 'C1', evidence_id: 'ORIGINAL', quote: '原文', claim: '判断', relation: 'supports' },
  ] });
  delete result.steps[4].citation_indexes;
  result.steps[4].citation_ids = ['missing-C2'];
  let calls = 0;
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原文。', question: '如何判断？',
  }, async () => { calls += 1; return modelReply(result); });

  assert.equal(outcome.status, 502);
  assert.equal(calls, 1);
  assert.match(outcome.payload.message, /step_shape_or_citation_index_invalid/);
  assert.equal(outcome.payload.provider_output.content, JSON.stringify(result));
  assert.equal(outcome.payload.format_repair, null);
  assert.equal(outcome.payload.trace.request_body.messages[1].content, JSON.stringify({
    original_text: '原文。', question: '如何判断？',
  }));
});

test('emendation candidate requires a nonblank reading; other types preserve optional text', async () => {
  const input = { mode: 'v1', original_text: '原文。', question: '是否异读？' };
  const candidate = collationResult({ conclusion_type: 'emendation_candidate', proposed_reading: '异字' });
  assert.equal((await generate(baseConfig, input, async () => modelReply(candidate))).status, 200);
  candidate.proposed_reading = '';
  assert.equal((await generate(baseConfig, input, async () => modelReply(candidate))).status, 502);
  candidate.proposed_reading = '  ';
  assert.equal((await generate(baseConfig, input, async () => modelReply(candidate))).status, 502);
  const keep = collationResult({ proposed_reading: '异字' });
  const keepOutcome = await generate(baseConfig, input, async () => modelReply(keep));
  assert.equal(keepOutcome.status, 200);
  assert.equal(keepOutcome.payload.result.conclusion_type, 'keep_text');
  assert.equal(keepOutcome.payload.result.proposed_reading, '异字');
});

test('interpretation gloss in proposed_reading is preserved without changing conclusion type', async () => {
  const result = collationResult({
    conclusion_type: 'interpretation',
    proposed_reading: '释为“困惑而无所得”',
  });
  result.steps[4].text = '倾向保留原字，只释为“困惑而无所得”，无须改字。';
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '甲字。', question: '甲字如何解释？',
  }, async () => modelReply(result));

  assert.equal(outcome.status, 200, outcome.payload.message);
  assert.equal(outcome.payload.result.conclusion_type, 'interpretation');
  assert.equal(outcome.payload.result.proposed_reading, '释为“困惑而无所得”');
  assert.equal(outcome.payload.provider_output.content, JSON.stringify(result));
});

test('cross-field conflict stays visible as returned content and unchanged raw output', async () => {
  const result = collationResult({
    conclusion_type: 'interpretation',
    proposed_reading: '将甲字改作乙字',
  });
  result.steps[4].text = '倾向将甲字改作乙字，作为校改候选。';
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '甲字。', question: '甲字是否需要校改？',
  }, async () => modelReply(result));

  assert.equal(outcome.status, 200);
  assert.equal(outcome.payload.result.conclusion_type, 'interpretation');
  assert.equal(outcome.payload.result.proposed_reading, '将甲字改作乙字');
  assert.equal(outcome.payload.result.steps[4].text, '倾向将甲字改作乙字，作为校改候选。');
  assert.equal(outcome.payload.provider_output.content, JSON.stringify(result));
});

test('proposed_reading remains a strict string field', async () => {
  for (const value of [null, ['异字'], { text: '异字' }]) {
    const result = collationResult({ proposed_reading: value });
    const outcome = await generate(baseConfig, {
      mode: 'v1', original_text: '甲字。', question: '如何理解？',
    }, async () => modelReply(result));
    assert.equal(outcome.status, 502);
    assert.match(outcome.payload.message, /proposed_reading_must_be_string/);
    assert.equal(outcome.payload.provider_output.content, JSON.stringify(result));
  }
});

test('field labels restore canonical step order and unsupported citation relations are rejected', async () => {
  const input = { mode: 'v1', original_text: '原文。', question: '如何读？' };
  const wrongOrder = collationResult();
  [wrongOrder.steps[0], wrongOrder.steps[1]] = [wrongOrder.steps[1], wrongOrder.steps[0]];
  const orderOutcome = await generate(baseConfig, input, async () => modelReply(wrongOrder));
  assert.equal(orderOutcome.status, 200);
  assert.deepEqual(orderOutcome.payload.result.steps.map((step) => step.field), [
    'problem_discovery', 'research_question', 'evidence_collection', 'reasoning', 'conclusion',
  ]);

  const wrongRelation = collationResult({
    citations: [{ evidence_id: 'ORIGINAL', quote: '原文', claim: '说明', relation: 'verified' }],
  });
  const relationOutcome = await generate(baseConfig, input, async () => modelReply(wrongRelation));
  assert.equal(relationOutcome.status, 502);
  assert.match(relationOutcome.payload.message, /citation_shape_invalid/);
});

test('retrieve passes optional collection filters and keeps the all-collections default', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'reading-harness-collections-'));
  const bridge = path.join(tmp, 'bridge.py');
  fs.writeFileSync(bridge, [
    'import json, sys',
    'payload = json.load(sys.stdin)',
    'assert payload["collections"] == ["external_mid", "external_low"]',
    'print(json.dumps({"ok":True,"data":{"items":[],"context":"","hit_count":0,"collections":payload["collections"]}}))',
  ].join('\n'), 'utf8');
  try {
    const outcome = await retrieve({
      PYTHON_BIN: process.env.V2_PYTHON_BIN || 'python',
      ROOT_DIR: tmp,
      READING_HARNESS_BRIDGE_FILE: bridge,
      READING_HARNESS_DB_FILE: path.join(tmp, 'unused.sqlite3'),
    }, {
      original_text: '原文', question: '如何判断？', collections: ['external_mid', 'external_low', 'external_mid'],
    });
    assert.equal(outcome.status, 200);
    assert.deepEqual(outcome.payload.data.collections, ['external_mid', 'external_low']);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('empty citations are marked as absent rather than verified', async () => {
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原文未决。', question: '判断？',
  }, async () => modelReply(collationResult({
    conclusion_type: 'insufficient_evidence', uncertainties: '证据不足。',
  })));
  assert.equal(outcome.status, 200);
  assert.equal(outcome.payload.citation_status, 'no_citations');
  assert.equal(outcome.payload.citations_all_valid, false);
});

test('uncertainties arrays normalize to newline text and absent values stay empty', async () => {
  const listed = await generate(baseConfig, {
    mode: 'v1', original_text: '原文。', question: '还需核查什么？',
  }, async () => modelReply(collationResult({ uncertainties: ['待核事项甲。', '待核事项乙。'] })));
  assert.equal(listed.status, 200, listed.payload.message);
  assert.equal(listed.payload.result.uncertainties, '待核事项甲。\n待核事项乙。');

  for (const value of [[], null, undefined]) {
    const result = collationResult();
    if (value === undefined) delete result.uncertainties;
    else result.uncertainties = value;
    const outcome = await generate(baseConfig, {
      mode: 'v1', original_text: '原文。', question: '还有未决处吗？',
    }, async () => modelReply(result));
    assert.equal(outcome.status, 200, outcome.payload.message);
    assert.equal(outcome.payload.result.uncertainties, '');
  }
});

test('uncertainties objects and non-string citation rationales are rejected', async () => {
  const badUncertainties = await generate(baseConfig, {
    mode: 'v1', original_text: '原文。', question: '还需核查什么？',
  }, async () => modelReply(collationResult({ uncertainties: { item: '不接受对象' } })));
  assert.equal(badUncertainties.status, 502);
  assert.match(badUncertainties.payload.message, /uncertainties_must_be_string_or_string_array/);

  const badRationale = await generate(baseConfig, {
    mode: 'v1', original_text: '原文。', question: '材料如何支持？',
  }, async () => modelReply(collationResult({ citations: [{
    evidence_id: 'ORIGINAL', quote: '原文', claim: '判断', rationale: { text: '不接受对象' }, relation: 'supports',
  }] })));
  assert.equal(badRationale.status, 502);
  assert.match(badRationale.payload.message, /citation_shape_invalid/);
});

test('truncated provider response keeps content, usage and finish reason', async () => {
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '原文未决。', question: '判断？',
  }, async () => ({
    ok: true,
    json: async () => ({
      choices: [{ finish_reason: 'length', message: { content: '{"analysis":"未完' } }],
      usage: { total_tokens: 32768 },
    }),
  }));
  assert.equal(outcome.status, 502);
  assert.equal(outcome.payload.provider_output.content, '{"analysis":"未完');
  assert.equal(outcome.payload.provider_output.finish_reason, 'length');
  assert.equal(outcome.payload.provider_output.usage.total_tokens, 32768);
});

test('overlong input is rejected before model call', async () => {
  let called = false;
  const outcome = await generate(baseConfig, {
    mode: 'v1', original_text: '文'.repeat(6001), question: '为什么？',
  }, async () => { called = true; });
  assert.equal(outcome.status, 400);
  assert.equal(outcome.payload.message, 'original_text_exceeds_6000_characters');
  assert.equal(called, false);
});

test('NFKC quote matching reports original codepoint coordinates', () => {
  const checks = checkCitations({
    citations: [{ evidence_id: 'ORIGINAL', quote: 'AB', claim: '字形' }],
  }, '甲ＡＢ乙', []);
  assert.equal(checks[0].valid, true);
  assert.equal(checks[0].match_start_cp, 1);
  assert.equal(checks[0].match_end_cp, 3);
});

test('quote locator includes combining mark needed for NFKC match', () => {
  const checks = checkCitations({
    citations: [{ evidence_id: 'ORIGINAL', quote: 'Á', claim: '组合字' }],
  }, '甲A\u0301乙', []);
  assert.equal(checks[0].valid, true);
  assert.equal(checks[0].match_start_cp, 1);
  assert.equal(checks[0].match_end_cp, 3);
  assert.equal(Array.from('甲A\u0301乙').slice(checks[0].match_start_cp, checks[0].match_end_cp).join('').normalize('NFKC'), 'Á');
});

test('at most two generation calls can be active', async () => {
  let release;
  let entered = 0;
  const gate = new Promise((resolve) => { release = resolve; });
  const pendingFetch = async () => {
    entered += 1;
    await gate;
    return modelReply(collationResult());
  };
  const input = { mode: 'v1', original_text: '甲。', question: '何意？' };
  const first = generate(baseConfig, input, pendingFetch);
  const second = generate(baseConfig, input, pendingFetch);
  const third = await generate(baseConfig, input, pendingFetch);
  assert.equal(entered, 2);
  assert.equal(third.status, 429);
  release();
  assert.equal((await first).status, 200);
  assert.equal((await second).status, 200);
});

test('independent simplified and traditional query terms yield the same variant set', () => {
  for (const [traditional, simplified] of [
    ['學問', '学问'], ['經義', '经义'], ['書卷', '书卷'],
    ['廣東', '广东'], ['體例', '体例'],
  ]) {
    const fromTraditional = buildQueryVariants(traditional, traditional);
    const fromSimplified = buildQueryVariants(simplified, simplified);
    assert.deepEqual(new Set(fromTraditional.original_text), new Set([traditional, simplified]));
    assert.deepEqual(new Set(fromSimplified.original_text), new Set([traditional, simplified]));
    assert.deepEqual(new Set(fromTraditional.question), new Set(fromSimplified.question));
    assert.equal(fromTraditional.original_text[0], traditional);
    assert.equal(fromSimplified.original_text[0], simplified);
  }
});

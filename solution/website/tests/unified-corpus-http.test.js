const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const config = require('../src/config');
const { createServer } = require('../src/http-server');

const databasesAvailable = fs.existsSync(config.CORPUS_DB_FILE)
  && fs.existsSync(config.READING_HARNESS_DB_FILE);

async function withServer(run) {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  try {
    return await run(`http://127.0.0.1:${address.port}`);
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
}

async function postSearch(baseUrl, payload) {
  const response = await fetch(`${baseUrl}/api/corpus/unified-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return { status: response.status, body: await response.json() };
}

test('unified corpus endpoint rejects an empty explicit range', async () => {
  await withServer(async (baseUrl) => {
    const result = await postSearch(baseUrl, {
      query: '任意词', mode: 'unified', collections: [],
    });
    assert.equal(result.status, 400);
    assert.equal(result.body.message, 'no_collection_selected');
  });
});

test('original title mode searches document titles before limiting results', { skip: !databasesAvailable }, async () => {
  await withServer(async (baseUrl) => {
    const result = await postSearch(baseUrl, {
      query: '读书杂志', mode: 'title', collections: ['original'], limit: 8,
    });
    assert.equal(result.status, 200);
    assert.ok(result.body.items.length > 0);
    assert.ok(result.body.items.every((item) => item.match_scope === 'title'));
    assert.ok(result.body.items.some((item) => String(item.document_title).includes('读书杂志')));
    assert.equal(typeof result.body.counts.original.candidate_count, 'number');
    assert.equal('items' in result.body.counts.original, false);
  });
});

test('body mode keeps original body matches and external tier selection', { skip: !databasesAvailable }, async () => {
  await withServer(async (baseUrl) => {
    const original = await postSearch(baseUrl, {
      query: '读书杂志', mode: 'body', collections: ['original'], limit: 8,
    });
    assert.equal(original.status, 200);
    assert.ok(original.body.items.length > 0);
    assert.ok(original.body.items.every((item) => item.match_scope === 'body'));

    const sourcePage = await fetch(`${baseUrl}/api/reading-harness/sources?collection=external_high&limit=1`)
      .then((response) => response.json());
    const source = sourcePage.data.items[0];
    assert.ok(source?.source_id);
    const chunks = await fetch(`${baseUrl}/api/reading-harness/chunks?source_id=${encodeURIComponent(source.source_id)}&limit=30`)
      .then((response) => response.json());
    const sourceChunk = chunks.data.items.find((item) => /[\p{Script=Han}]{4,}/u.test(item.preview || ''));
    assert.ok(sourceChunk, 'fixture source should contain a Chinese text chunk');
    const firstChunk = await fetch(`${baseUrl}/api/reading-harness/chunk?chunk_id=${encodeURIComponent(sourceChunk.chunk_id)}`)
      .then((response) => response.json());
    const query = String(firstChunk.data.full_text).match(/[\p{Script=Han}]{4,}/u)?.[0];
    assert.ok(query, 'fixture source should provide a Chinese body query');

    const external = await postSearch(baseUrl, {
      query,
      mode: 'body',
      collections: ['external_high'],
      limit: 8,
    });
    assert.equal(external.status, 200);
    assert.ok(external.body.items.every((item) => item.collection === 'external_high'));
    assert.ok(external.body.items.every((item) => item.kind === 'external_chunk'));
    assert.equal(external.body.counts.external_body.result_limit, 6);
    assert.equal('items' in external.body.counts.external_body, false);
  });
});

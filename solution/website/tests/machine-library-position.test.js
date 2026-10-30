const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { once } = require('node:events');
const { createServer } = require('../src/http-server');
const { machineQuery, getMachineLibrary } = require('../src/machine-library');

test('position query validation keeps the default unrestricted', () => {
  assert.equal(machineQuery({query: {}}).position, 'any');
  assert.equal(machineQuery({query: {position: 'target'}}).position, 'target');
  assert.throws(() => machineQuery({query: {position: 'left-ish'}}), /检索位置/);
});

test('a missing machine library never falls back to the old dictionary', async () => {
  const payload = await getMachineLibrary({MACHINE_LIBRARY_DB_FILE: path.join(__dirname, 'missing-machine-library.sqlite3')}, 'meta');
  assert.equal(payload.available, false);
  assert.equal(payload.ok, false);
});

test('position filters complete claims before grouping and preserve ordinary mentions', { skip: !fs.existsSync(path.join(__dirname, '../runtime-bundle/machine-library.sqlite3')) }, async () => {
  const server = createServer(); server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const get = async (q, position = 'any', view = 'terms', extra = '') => {
    const response = await fetch(`${base}/api/machine/search?q=${encodeURIComponent(q)}&position=${position}&view=${view}${extra}`);
    assert.equal(response.status, 200);
    return response.json();
  };
  try {
    const all = await get('農');
    const source = await get('農', 'source');
    const target = await get('農', 'target');
    assert.equal(all.relation_group_count, 6);
    assert.equal(source.relation_group_count, 3);
    assert.equal(target.relation_group_count, 3);
    assert.ok(source.items.every(item => item.left_form.includes('農')));
    assert.ok(target.items.every(item => item.right_form.includes('農')));
    assert.deepEqual([...new Set([...source.matched_claim_ids, ...target.matched_claim_ids])].sort(), [...all.matched_claim_ids].sort());
    assert.equal(source.mentions.total, all.mentions.total);
    assert.equal(target.mentions.total, all.mentions.total);
    for (const q of ['農', '勉', '毋 無']) {
      for (const position of ['source', 'target']) {
        const terms = await get(q, position);
        const cases = await get(q, position, 'cases');
        assert.deepEqual(terms.matched_claim_ids, cases.matched_claim_ids, `${q}/${position}`);
        assert.equal(terms.case_count, cases.total);
        if (q === '毋 無') {
          assert.equal(terms.relation_group_count, 1);
          assert.equal(terms.matched_claim_count, 2);
        }
      }
    }
    for (const position of ['source', 'target']) {
      assert.equal((await get('農 努', position)).matched_claim_count, 0);
      assert.ok((await get('農 努', position, 'terms', '&match=any')).matched_claim_count > 0);
    }
    const first = await get('之', 'source');
    const second = await get('之', 'source', 'terms', '&page=2');
    assert.equal(first.page, 1);
    assert.equal(second.page, 2);
    assert.ok(first.items.every(a => !second.items.some(b => a.id === b.id)));
    assert.deepEqual(first.matched_claim_ids, second.matched_claim_ids);
    assert.equal((await fetch(`${base}/api/machine/search?position=invalid`)).status, 400);
    for (const route of ['terms', 'cases', 'case']) {
      assert.equal((await fetch(`${base}/api/parser-candidates/${route}`)).status, 404);
    }
    for (const source of ['main', 'all', 'parser']) {
      assert.match(await (await fetch(`${base}/cases?source=${source}`)).text(), /assets\/js\/machine-library.js/);
    }
    assert.match(await (await fetch(`${base}/cases?source=annotation`)).text(), /assets\/js\/cases.js/);
  } finally {
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
});

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { once } = require('node:events');
const { createServer } = require('../src/http-server');
const { PAGES, resolvePage } = require('../src/site-routes');
const WEB = path.join(__dirname, '../web');
test('canonical pages load directly, with absolute assets and one consistent navigation', async () => {
  const server = createServer(); server.listen(0, '127.0.0.1'); await once(server,'listening');
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    for (const route of Object.keys(PAGES)) {
      const response = await fetch(base + route);
      assert.equal(response.status,200,route);
      const html = await response.text();
      const nav = html.match(/<nav class="nav"[\s\S]*?<\/nav>/)[0];
      for (const target of ['/', '/audit','/cases','/terms','/corpus','/knowledge']) assert.ok(nav.includes('href="'+target+'"'),route+target);
      assert.doesNotMatch(html,/src="\.\/|href="\.\//);
      for (const m of html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)) assert.equal((await fetch(base+m[1])).status,200,m[1]);
    }
    assert.equal((await fetch(base+'/case?source=v2&id=candidate-shell%3A%E8%AF%BB%2F%3F')).status,200);
    assert.equal((await fetch(base+'/does-not-exist')).status,404);
  } finally { server.closeAllConnections(); await new Promise(r=>server.close(r)); }
});
test('retired pages and one-shot AI endpoint have no compatibility path', async () => {
  const server = createServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    for (const old of ['/database.html?view=cases', '/annotation.html', '/v2-database.html',
      '/annotation-workbench.html?case=x', '/ai-annotation.html', '/v2-acceptance.html',
      '/web/case.html?id=1', '/case.html?id=1', '/index.html']) {
      assert.equal(resolvePage(new URL(old, base)), null);
      const response = await fetch(base + old, { redirect: 'manual' });
      assert.equal(response.status, 404, old);
      assert.equal(response.headers.has('location'), false);
    }
    assert.equal((await fetch(base + '/api/ai/annotation', { method: 'POST' })).status, 404);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});

test('page documents contain one navigation placeholder and no copied menu', () => {
  for (const file of Object.values(PAGES)) {
    const html = fs.readFileSync(path.join(WEB, file), 'utf8');
    assert.equal((html.match(/<!--site-navigation-->/g) || []).length, 1, file);
    assert.doesNotMatch(html, /class="nav-links"/);
  }
});

test('every shipped frontend script has an active page consumer', () => {
  const documents = Object.values(PAGES).map(file => fs.readFileSync(path.join(WEB, file), 'utf8')).join('\n');
  for (const file of fs.readdirSync(path.join(WEB, 'assets/js')).filter(file => file.endsWith('.js'))) {
    assert.ok(documents.includes('/assets/js/' + file), file + ' is not loaded by any active page');
  }
});

test('review retains decisions, evidence context, write arming and in-page case selection',()=>{
  const html=fs.readFileSync(path.join(WEB,'audit.html'),'utf8');
  for(const value of ['fiveStepRecommended','fiveStepCaseSearch','fiveStepEvidenceOverview','fiveStepWriteArm','value="reviewed"','value="needs_revision"','value="uncertain"']) assert.ok(html.includes(value),value);
  const script=fs.readFileSync(path.join(WEB,'assets/js/five-step-audit.js'),'utf8');
  assert.ok(script.includes('offerDraftRestore'));
  assert.ok(script.includes('AuditDraft.clear(state.caseId)'));
  assert.ok(script.includes('state.writeArmed = false'));
});

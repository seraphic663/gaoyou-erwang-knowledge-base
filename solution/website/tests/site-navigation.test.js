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
test('old URLs preserve record identity and search filters without old documents', () => {
  const inputs = [
    ['/database.html?view=cases&q=造&page=3', '/cases', {source:'main',q:'造',page:'3'}],
    ['/v2-database.html?case=candidate-shell%3Aa%2Fb%3Fc', '/case', {source:'v2',id:'candidate-shell:a/b?c'}],
    ['/web/annotation-workbench.html?case=x%3Ay', '/audit', {case:'x:y'}],
    ['/annotation.html?annotator=a&annotator=b', '/cases', {source:'annotation'}],
    ['/case.html?id=42', '/case', {source:'main',id:'42'}],
    ['/database.html?view=schema', '/quality', {view:'schema'}],
  ];
  for (const [old,target,params] of inputs) {
    const result=resolvePage(new URL(old,'http://localhost'));
    const u=new URL(result.redirect,'http://localhost');
    assert.equal(u.pathname,target);
    for(const [k,v] of Object.entries(params)) assert.equal(u.searchParams.get(k),v);
  }
  for(const file of ['database','annotation','v2-database','annotation-workbench','ai-annotation','v2-acceptance']) assert.equal(fs.existsSync(path.join(WEB,file+'.html')),false);
});
test('review retains decisions, evidence context, write arming and in-page case selection',()=>{
  const html=fs.readFileSync(path.join(WEB,'audit.html'),'utf8');
  for(const value of ['fiveStepRecommended','fiveStepCaseSearch','fiveStepEvidenceOverview','fiveStepWriteArm','value="reviewed"','value="needs_revision"','value="uncertain"']) assert.ok(html.includes(value),value);
  const script=fs.readFileSync(path.join(WEB,'assets/js/five-step-audit.js'),'utf8');
  assert.ok(script.includes('offerDraftRestore'));
  assert.ok(script.includes('AuditDraft.clear(state.caseId)'));
  assert.ok(script.includes('state.writeArmed = false'));
});

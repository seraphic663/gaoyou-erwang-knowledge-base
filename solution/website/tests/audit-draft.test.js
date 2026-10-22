const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
test('draft recovery is scoped to case and tab; clearing a saved draft keeps others',()=>{
 const values=new Map(),window={};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/assets/js/audit-draft.js'),'utf8'),{window,sessionStorage:{getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)}});
 const d=window.AuditDraft;
 d.write('a',{generation:{case_fingerprint:'source-a'},reviewedSteps:[{text:'修改意见'}]});
 d.write('b',{generation:{case_fingerprint:'source-b'}});
 assert.equal(d.read('a').reviewedSteps[0].text,'修改意见');assert.equal(d.read('b').generation.case_fingerprint,'source-b');
 d.clear('a');assert.equal(d.read('a'),null);assert.ok(d.read('b'));
});

test('malformed or wrong-case drafts cannot enter the review form', () => {
  const values = new Map();
  const window = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/assets/js/audit-draft.js'), 'utf8'), {
    window,
    sessionStorage: {
      getItem: key => values.get(key),
      setItem: (key, value) => values.set(key, value),
      removeItem: key => values.delete(key),
    },
  });
  const draft = window.AuditDraft;
  values.set(draft.key('a'), '{"version":1,"caseId":"b"}');
  assert.equal(draft.read('a'), null);
  draft.write('a', { generation: { draft: [{ field: 'first' }] }, reviewedSteps: [] });
  assert.equal(draft.read('a', ['first']), null);
  draft.write('a', { generation: { draft: [{ field: 'first' }] }, reviewedSteps: [{ field: 'first' }] });
  assert.ok(draft.read('a', ['first']));
});

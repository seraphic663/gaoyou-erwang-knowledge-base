// Explicit isolated-fixture integration check, never run against production.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {once}=require('node:events');
if(!process.env.V2_DB_FILE?.includes('fixture-copy')) throw new Error('Requires an isolated fixture-copy database');
const {createServer}=require('../src/http-server');
const {fingerprintV2Case,STEPS,PROMPT_VERSION}=require('../src/v2-five-step-audit');
(async()=>{
 const server=createServer();server.listen(0,'127.0.0.1');await once(server,'listening');
 const base='http://127.0.0.1:'+server.address().port;
 const req=async(p,body,method='POST')=>{const r=await fetch(base+p,body?{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);return {status:r.status,data:await r.json()};};
 try{
  const id='fixture_dushu_0001',item=(await req('/api/v2/case?id='+id)).data;
  const payload={case_id:id,reviewer:'navigation-integration-test',operation_id:'site-nav-'+Date.now(),model_requested:'deepseek-flash',model_returned:'deepseek-flash',reasoning_effort:'high',prompt_version:PROMPT_VERSION,case_fingerprint:fingerprintV2Case(item),generated_at:new Date().toISOString(),ai_draft:STEPS.map(x=>({field:x.field,text:'隔离副本验证材料',evidence_refs:[],review_questions:[]})),reviewed_steps:STEPS.map(x=>({field:x.field,text:'隔离副本验证意见',status:'accepted',comment:''})),overall_decision:'uncertain',overall_note:'隔离测试，不调用模型，不写线上'};
  assert.equal((await req('/api/v2/five-step-audits',{...payload,case_fingerprint:'bad'})).status,409);
  const saved=await req('/api/v2/five-step-audits',payload);
  assert.equal(saved.status,200,JSON.stringify(saved.data));
  const auditId=saved.data.audit_id;assert.ok(auditId);
  assert.equal((await req('/api/v2/five-step-audits',payload)).data.audit_id,auditId);
  const edit=await req('/api/v2/five-step-audits',{audit_id:auditId,case_id:id,reviewer:payload.reviewer,operation_id:payload.operation_id+'-edit',reviewed_steps:payload.reviewed_steps,overall_decision:'uncertain',overall_note:'revision'},'PATCH');
  assert.equal(edit.status,200,JSON.stringify(edit.data));const revised=edit.data.audit_id;
  assert.equal((await req('/api/v2/five-step-audits',{audit_id:revised,deleted_by:payload.reviewer,operation_id:payload.operation_id+'-delete'},'DELETE')).status,200);
  assert.equal((await req('/api/v2/five-step-audits',{mode:'restore',audit_id:revised,restored_by:payload.reviewer,operation_id:payload.operation_id+'-restore'})).status,200);
  const history=(await req('/api/v2/five-step-audits?case_id='+id)).data;
  assert.ok(history.records.some(r=>r.audit_id===auditId&&r.record_state==='superseded'));
  assert.ok(history.records.some(r=>r.audit_id===revised&&r.record_state==='active'));
  console.log(JSON.stringify({ok:true,prompt:PROMPT_VERSION,staleFingerprintRejected:true,idempotent:true,revisionDeleteRestore:true}));
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
})().catch(error=>{console.error(error);process.exitCode=1;});

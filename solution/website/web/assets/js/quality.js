(async()=>{
 const root=document.querySelector('#qualityMain');
 const result=await Promise.allSettled([requestJson('/api/schema'),requestJson('/api/v2/summary')]);
 const section=(title,content)=>'<section class="card"><h2>'+title+'</h2>'+content+'</section>';
 root.innerHTML=result.map((entry,i)=>{
  if(entry.status==='rejected') return section(i?'V2 质量报告':'主库结构','<p>'+escapeHtml(entry.reason.message)+'</p>');
  const data=entry.value;
  const summary=i?'<p>验收状态：'+escapeHtml(data.overall_status)+'；结构通过不代表人工审定。</p><dl>'+Object.entries(data.counts||{}).map(([k,v])=>'<dt>'+escapeHtml(k)+'</dt><dd>'+escapeHtml(v)+'</dd>').join('')+'</dl>':'<p>主数据库的字词、案例和证据结构。</p>';
  return section(i?'V2 质量报告':'主库结构',summary+'<details><summary>完整报告与字段</summary><pre class="site-raw">'+escapeHtml(JSON.stringify(data,null,2))+'</pre></details>');
 }).join('');
})();

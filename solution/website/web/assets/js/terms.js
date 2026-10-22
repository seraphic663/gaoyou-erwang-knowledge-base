(async()=>{
 const p=new URLSearchParams(location.search),form=document.querySelector('#termSearch'),root=document.querySelector('#termResults');
 form.elements.q.value=p.get('q')||'';
 form.onsubmit=e=>{e.preventDefault();location.href='/terms?'+new URLSearchParams(new FormData(form));};
 form.elements.mode.value=p.get('mode')||'fulltext';
 requestJson('/api/browser/bootstrap').then(data=>{form.elements.category.innerHTML=(data.termCategories||[]).map(v=>'<option value="'+escapeHtml(v.value)+'">'+escapeHtml(v.label)+'</option>').join('');form.elements.category.value=p.get('category')||'all';}).catch(()=>{});
 try{
  const q=new URLSearchParams({view:'terms',mode:p.get('mode')||'fulltext',category:p.get('category')||'all',q:p.get('q')||'',page:p.get('page')||'1',pageSize:'30'});
  const data=await requestJson('/api/browser?'+q);
  root.innerHTML='<p>'+data.total+' 条字词</p><div class="grid grid-2">'+data.items.map(item=>'<article class="card"><h2>'+Site.link(Site.url('/term',{id:item.id,return:Site.current()}),item.term)+'</h2><p>'+escapeHtml(item.coreMeaning||item.notes||'')+'</p><div class="site-actions">'+(item.relatedCases||[]).map(c=>Site.link(Site.caseUrl('main',c.id),c.displayTitle||c.title||'关联案例')).join('')+'</div></article>').join('')+'</div><div class="site-actions">'+[data.page>1?[data.page-1,'上一页']:null,data.page<data.totalPages?[data.page+1,'下一页']:null].filter(Boolean).map(([page,label])=>{const next=new URLSearchParams(p);next.set('page',page);return Site.link('/terms?'+next,label);}).join('')+'第 '+data.page+' / '+data.totalPages+' 页</div>';
 }catch(error){root.textContent='字词读取失败：'+error.message;}
})();

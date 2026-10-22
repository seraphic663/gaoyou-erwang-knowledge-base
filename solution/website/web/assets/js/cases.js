(async () => {
  if (['#quality','#report'].includes(location.hash)) { location.replace('/quality'); return; }
  const params = new URLSearchParams(location.search), source = params.get('source') || 'all';
  const form = document.querySelector('#caseSearch'), results = document.querySelector('#caseResults');
  form.elements.q.value = params.get('q') || '';
  form.elements.source.value = ['all', 'main', 'annotation', 'v2'].includes(source) ? source : 'all';
  const labels = { main: '主库材料', annotation: '人工标注材料', v2: 'V2 工作材料' };
  form.onsubmit = event => { event.preventDefault(); location.href = '/cases?' + new URLSearchParams(new FormData(form)); };
  requestJson('/api/annotation/bootstrap').then(data=>{
    for(const [field,values] of [['annotator',data.annotators],['origin',data.origins]]) {
      form.elements[field].innerHTML=(values||[]).map(v=>'<option value="'+escapeHtml(v.value)+'">'+escapeHtml(v.label)+'</option>').join('');
      form.elements[field].value=params.get(field)||'all';
    }
  }).catch(()=>{});
  form.elements.machine_status.value=params.get('machine_status')||'';
  const selected = source === 'all' ? Object.keys(labels) : [source];
  if (!selected.every(s => labels[s])) { results.textContent = '未知材料来源，请重新选择。'; return; }
  results.innerHTML = selected.map(s => '<section class="site-source" id="source-' + s + '"><h2>' + labels[s] + '</h2><p>正在读取……</p></section>').join('');
  await Promise.all(selected.map(async s => {
    const section = document.querySelector('#source-' + s);
    try {
      const page = params.get('page_' + s) || params.get('page') || '1';
      const q = new URLSearchParams({ q: params.get('q') || '', page, pageSize: '20' });
      if (s === 'main') { q.set('view', 'cases'); q.set('mode', 'fulltext'); q.set('category', 'all'); }
      if (s === 'v2') for (const key of ['source_work', 'machine_status']) if (params.has(key)) q.set(key, params.get(key));
      if (s === 'annotation') for (const key of ['document', 'method', 'annotator', 'origin']) params.getAll(key).forEach(v => q.append(key, v));
      const payload = await requestJson(({main:'/api/browser',annotation:'/api/annotation',v2:'/api/v2/cases'})[s] + '?' + q);
      if(s==='v2') { form.elements.source_work.innerHTML='<option value="">全部来源</option>'+(payload.source_works||[]).map(v=>'<option value="'+escapeHtml(typeof v==='string'?v:v.value||v.source_work||v.label)+'">'+escapeHtml(typeof v==='string'?v:v.label||v.source_work||v.value)+'</option>').join(''); form.elements.source_work.value=params.get('source_work')||''; }
      const items = payload.items || [], pages = payload.totalPages || payload.page_count || 1, active = Number(payload.page || 1);
      section.innerHTML = '<h2>' + labels[s] + ' <small>' + Number(payload.total || 0) + ' 条</small></h2><p class="compact-note">保留原始来源身份；不同来源之间可能存在迁移或重叠记录，不合并计作独立案例。</p>' + items.map((item, i) => {
        const id = s === 'v2' ? item.case_id : item.id, title = item.displayTitle || item.case_title || item.title || '未题名案例';
        return '<article class="card site-case"><h3>' + escapeHtml(title) + '</h3><p>' + escapeHtml(item.problem || item.target_text || item.conclusion || item.source_excerpt || '') + '</p><p class="compact-note">' + escapeHtml(item.source_work || item.origin || item.erwangWorkTitle || '') + ' · ' + escapeHtml(item.human_status || item.status || item.certainty || '待核') + '</p><div class="site-actions">' + Site.link(Site.caseUrl(s, id), '查看案例') + '<span id="audit-' + s + '-' + i + '">正在核对审校关联……</span></div></article>';
      }).join('') + (!items.length ? '<p>没有匹配记录。</p>' : '') + '<div class="site-actions">' + [active > 1 ? [active - 1, '上一页'] : null, active < pages ? [active + 1, '下一页'] : null].filter(Boolean).map(([p, label]) => { const target = new URLSearchParams(params); target.set('page_' + s, p); return Site.link('/cases?' + target, label); }).join('') + '<span>第 ' + active + ' / ' + pages + ' 页</span></div>';
      if (items.length) {
        try {
          const targets = await Site.auditLinks(s, items.map(item => s === 'v2' ? item.case_id : item.id));
          items.forEach((item, i) => { document.querySelector('#audit-' + s + '-' + i).innerHTML = Site.auditMarkup(targets[s === 'v2' ? item.case_id : item.id]); });
        } catch { items.forEach((_, i) => { document.querySelector('#audit-' + s + '-' + i).textContent = '审校关联暂不可用，仍可阅读原记录'; }); }
      }
    } catch (error) { section.innerHTML = '<h2>' + labels[s] + '</h2><p role="alert">' + escapeHtml(error.message) + '</p>'; }
  }));
})();

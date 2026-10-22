(async () => {
  const params = new URLSearchParams(location.search), source = params.get('source') || 'main', id = params.get('id');
  const root = document.querySelector('#caseReader'), title = document.querySelector('#detailTitle');
  if (!['main','annotation','v2'].includes(source) || !id) { root.textContent = '来源或案例编号无效。'; return; }
  const block = (heading, content) => '<section class="card"><h2>' + heading + '</h2>' + content + '</section>';
  const text = value => '<p class="detail-paragraph">' + escapeHtml(value || '未记录') + '</p>';
  const recordData = (value) => '<details class="fold-card"><summary>查看完整来源字段</summary><pre class="site-raw">' + escapeHtml(JSON.stringify(value, null, 2)) + '</pre></details>';
  try {
    const payload = await requestJson(({main:'/api/case',annotation:'/api/annotation/detail',v2:'/api/v2/case'})[source] + '?id=' + encodeURIComponent(id));
    const item = source === 'annotation' ? payload.item : payload;
    title.textContent = item.displayTitle || item.case_title || item.title || '案例详情';
    const terms = item.terms || [], evidence = item.evidences || [], steps = item.process_steps || item.processSteps || [];
    const links = terms.map(t => source === 'main' && t.id ? Site.link(Site.url('/term', { id:t.id, return:Site.current() }), t.term || t.termName || '') : '<span class="tag">' + escapeHtml(t.term || t.source_term || t.target_term || '') + '</span>').join(' ');
    let original = '';
    for (const [label, passage] of [['来源原文',item.source_passage],['目标原文',item.target_passage]]) if (passage) original += block(label, text(passage.raw_text || passage.passage_text || passage.text || passage.content) + recordData(passage));
    root.innerHTML = '<div class="site-actions" id="caseActions"><span class="tag">' + ({main:'主库材料',annotation:'人工标注材料',v2:'V2 工作材料'})[source] + '</span><span id="caseAudit">核对审校关联中……</span></div>' + block('问题与判断',text(item.problem || item.case_data?.research_question || item.target_text) + text(item.claim || item.conclusion || item.case_data?.conclusion)) + original + block('出处与状态',text(item.source_work || item.erwangWorkTitle || item.source_document?.source_file_name) + text([item.machine_status,item.human_status,item.status,item.certainty].filter(Boolean).join(' · '))) + block('相关字词',links || text('未记录')) + block('证据',evidence.map(e=>'<blockquote>' + text(e.quote || e.evidenceQuote || e.text) + '<footer>' + escapeHtml(e.source_work || e.work || e.workTitle || '') + '</footer></blockquote>' + recordData(e)).join('') || text('未记录')) + block('考据过程',text(item.processText) + steps.map(s=>text((s.field_name || s.step_type || '') + '：' + (s.step_text || s.text || ''))).join('')) + recordData(item);
    document.querySelector('#caseActions').insertAdjacentHTML('beforeend', Site.link(Site.url('/corpus', source === 'v2' ? {case_id:id,return:Site.current()} : {q:item.target_text || item.targetText || item.title || '',return:Site.current()}), source === 'v2' ? '查看本案原文与检索材料' : '检索相关原文') + Site.link(Site.url('/knowledge',{return:Site.current()}),'查看训诂方法'));
    if (source === 'v2' && item.related_cases?.length) root.insertAdjacentHTML('beforeend',block('相关案例',item.related_cases.map(c=>Site.link(Site.caseUrl('v2',c.case_id),c.case_title)).join(' ')));
    try { const mappings = await Site.auditLinks(source,[id]); document.querySelector('#caseAudit').innerHTML = Site.auditMarkup(mappings[id]); } catch { document.querySelector('#caseAudit').textContent = '暂时无法核对审校关联'; }
  } catch (error) { root.textContent = '无法读取案例：' + error.message; }
})();

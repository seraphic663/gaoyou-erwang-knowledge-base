const architecture = require('./architecture');
const comparison = require('./compare');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const port = Number(process.env.PORT || 3190);
const names = {map:'页面跳转关系图',index:'专题首页',database:'主数据库',annotation:'人工标注库',corpus:'通用语料库','v2-database':'V2 工作库','annotation-workbench':'五步释证',knowledge:'训诂知识',term:'字词详情',case:'案例详情','ai-annotation':'旧 AI 入口','v2-acceptance':'旧验收入口',cases:'案例库',terms:'字词库',audit:'释证与审校',quality:'质量报告'};
const currentNav=['index','database','annotation','corpus','v2-database','annotation-workbench','knowledge'];
const proposedNav=['index','audit','cases','terms','corpus','knowledge'];
const titles=(mode,key)=> mode==='proposed'&&key==='corpus'?'原典检索':names[key];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(mode,key,url){
 const proposed=mode==='proposed', nav=proposed?proposedNav:currentNav;
 const link=(page,label,query='')=>`<a class="action" href="/${mode}/${page}.html${query}">${esc(label||titles(mode,page))}<span>↗</span></a>`;
 const block=(title,body)=>`<section class="block"><h2>${title}</h2>${body}</section>`;
 const links=(...items)=>`<div class="actions">${items.join('')}</div>`;
 const sample=`<span class="tag">演示案例 · 非真实库映射</span><h3>造舟于河</h3><p>围绕“造”应训“比次”还是“至”，查看原文、证据与论证过程。</p>`;
 const caseId=proposed?'demo-zaozhou':'v2-demo-zaozhou';
 const auditTarget=proposed?'audit':'annotation-workbench';
 const selected=url.searchParams.has('case');
 const goAudit=link(auditTarget,'直接开始本案释证与审校',`?case=${caseId}`);
 let desc='',body='';
 if(key==='map'){desc='可点击的全量页面关系、首页最短路径，以及两版合并与跳转变化对照。';body=architecture.diagram(mode);}
 if(key==='index'){
  desc=proposed?'直接开始释证与审校，或者从字词、案例、原典进入研究。':'了解项目、阅读代表案例，并从不同数据库入口继续查阅。';
  body=block(proposed?'今天从哪里开始？':'研究对象与使用路径',`<p>高邮二王考据材料的整理、释证与复核。</p>${links(...(proposed?[link('audit','开始释证与审校'),link('cases','查案例'),link('terms','查字词'),link('corpus','查原文')]:[link('database','进入主数据库'),link('annotation'),link('v2-database','选择 V2 案例'),link('annotation-workbench','开始五步审校'),link('knowledge')]))}`)+block('封面个案：造舟于河',`<p>发疑 → 设问 → 取证 → 释理 → 结论。当前版在首页展示案例讲解；建议版可直接进入案例或审校。</p>${links(...(proposed?[link('case','阅读代表案例','?id=demo-zaozhou'),goAudit]:[link('knowledge','查看训诂方法'),link('database','浏览更多案例','?view=cases')]))}`)+block('字词与案例试查',`${sample}${links(link('term','查看“造”的字词详情','?id=zao'),link('case','查看案例详情','?id=demo-zaozhou'))}`);
 }
 if(['database','cases','terms'].includes(key)){
  const terms=key==='terms'||(key==='database'&&url.searchParams.get('view')!=='cases');
  desc=key==='database'?'主数据库的字词、案例和结构视图；人工标注及 V2 材料仍由独立入口浏览。':key==='cases'?'将不同来源案例集中到一个入口；来源与审校状态仍分别标明。':'直接按字词寻找义项、证据和关联案例。';
  body=(key==='database'?`<div class="tabs">${link('database','字词视图','?view=terms')}${link('database','案例视图','?view=cases')}${link('database','数据库结构','?view=schema')}</div>`:'');
  if(url.searchParams.get('view')==='schema')body+=block('数据库结构','<p>这里说明字词、案例、证据之间的数据关系。它是主数据库的辅助视图。</p>');
  else if(terms)body+=block('字词检索',`<p>示例字词：造。核心义项：比次。关联案例：造舟于河。</p>${links(link('term','查看字词详情','?id=zao'),link('case','查看关联案例','?id=demo-zaozhou'))}`);
  else body+=block('案例浏览',`${proposed?'<div class="filters"><label>来源 <select id="source-filter"><option value="all">全部来源</option><option value="main">主数据库</option><option value="human">人工标注</option><option value="v2">V2 工作材料</option></select></label><span>筛选仅切换示例记录，不合并数据身份。</span></div>':''}${['main','human','v2'].filter(s=>proposed||s==='main').map((s,i)=>`<article class="record" data-source="${s}"><span class="tag">${{main:'主数据库 · 示例记录',human:'人工标注 · 待核材料',v2:'V2 · 机器草稿'}[s]}</span><h3>${i?'相关考据示例 '+i:'造舟于河'}</h3><p>${s==='human'?'尚未建立可靠 V2 对应关系，此示例不开放审校。':'阅读问题、原文、证据和结论；示例已配置可审校映射。'}</p>${links(link('case','查看详情',`?id=${s}-demo&source=${s}`),...(proposed&&s!=='human'?[goAudit]:[]))}</article>`).join('')}`);
  if(proposed&&key==='cases')body+=block('辅助信息',`<p>质量报告与数据库结构供维护时查阅。</p>${link('quality','查看质量报告与结构')}`);
 }
 if(key==='term'){
  desc='阅读一个字词的义项、类别、相关案例和证据概况。';
  body=block('造',`<p>示例义项：比次。相关材料来自“造舟于河”考释。</p>`)+block('关联案例',`${sample}${links(link('case','阅读关联案例','?id=demo-zaozhou'),...(proposed?[goAudit,link('cases','查看该字词的更多案例','?term=zao')]:[]))}`);
 }
 if(key==='case'){
  const source=url.searchParams.get('source')||'main';
  desc=proposed?'统一的案例阅读落点。阅读不是进入审校的必经步骤；按材料来源展示实际可用信息。':'主数据库案例详情，阅读问题、结论、出处与证据，并进入相关字词。';
  body=block('案例内容',`${sample}<p><b>问题：</b>“造”如何解释？</p><p><b>证据：</b>“造之言曹也，相比次之名也。”</p><p><b>结论：</b>本演示只说明页面职责，不作研究判断。</p><span class="tag">来源：${esc(source)} · 演示记录</span>`)+block('继续查阅或工作',links(link('term','查看相关字词“造”','?id=zao'),...(proposed?[link('corpus','定位本案原文','?passage=zaozhou&from=case'),link('knowledge','查看对应方法','?method=sound'),link('cases','查找相关案例','?related=zaozhou'),...(source!=='human'?[goAudit]:[])]:[])));
  if(proposed&&source==='human')body+=block('审校接入状态','<p>此演示记录尚无可靠 V2 映射，不能直接开始 AI 审校。人工标注来源也不等于已经审定。</p>');
 }
 if(key==='annotation'){
  desc='独立的人工标注材料浏览入口；案例详情在本页展开。';
  body=block('人工标注材料',`${sample}<details><summary>展开人工标注详情（仍在本页）</summary><p>判断、相关字词、证据、过程步骤与标注者信息。</p><p>当前架构没有指向对应主库或 V2 记录的内容跳转。</p></details>`);
 }
 if(key==='v2-database'){
  desc='查找 V2 案例，在本页阅读来源、证据与状态，再进入五步释证。';
  body=block('V2 案例浏览',`${sample}${links(goAudit)}<details ${selected?'open':''}><summary>查看案例详情（仍在本页）</summary><p>来源段落、目标典籍、证据、机器状态。</p>${goAudit}</details>`)+block('原典与质量',`${link('corpus','进入通用语料库')}<details><summary>查看质量报告（仍在本页）</summary><p>结构验收、原典登记与状态判定依据。结构通过不代表人工认可。</p></details>`);
 }
 if(key==='corpus'){
  desc=proposed?'检索原典正文，也可接收案例传来的段落定位；从命中材料直接进入阅读或审校。':'按正文片段寻找原文、出处与关联 V2 案例。';
  body=block(url.searchParams.has('passage')?'已定位：造舟于河对应段落':'原典检索示例',`<p>检索词：造舟</p><blockquote>造之言曹也，相比次之名也。</blockquote><p>出处示例：《经义述闻·左传下》。这里应提供原文、位置与上下文。</p>`)+block('关联案例',`${sample}${links(...(proposed?[link('case','阅读关联案例','?id=demo-zaozhou'),goAudit]:[link('v2-database','查看关联 V2 案例','?case=v2-demo-zaozhou#browse')]))}`);
 }
 if(key===auditTarget){
  desc=proposed?'核心工作入口：在一个页面选案、查看材料、模拟 AI 起草、逐步审核和保存。无需先经过案例详情。':'当前五步释证也支持直接选案；进入后生成五步草稿、人工审校并查看历史。';
  body=block('选择要审校的案例',`${sample}<button id="choose-case">${selected?'已选此案 · 重新载入':'选择此案，在本页开始'}</button>${!proposed?link('v2-database','查看完整 V2 工作库'):''}`)+`<section class="block" id="workspace" ${selected?'':'hidden'}><div class="section-top"><h2>当前案例 · 造舟于河</h2><span class="tag">全部为模拟操作</span></div><p>原文、证据与方法参考在本页提供，不需要为基本材料反复跳转。</p><blockquote>造之言曹也，相比次之名也。</blockquote><button id="generate">模拟生成五步草稿</button><div id="draft"></div><p id="save-state" role="status"></p>${links(...(proposed?[link('case','完整案例详情','?id=demo-zaozhou'),link('corpus','核对原文','?passage=zaozhou&from=audit')]:[link('v2-database','返回 V2 工作库','#browse')]))}</section>`;
 }
 if(key==='knowledge'){
  desc='阅读训诂术语、音义关系、方法与禁忌。';
  body=block('因声求义',`<p>通过语音关系联系词义，是阅读考据过程时使用的方法参考。</p>${proposed?links(link('cases','查看使用此方法的案例','?method=sound')):'<p>当前页面是独立参考资料，没有连到具体案例的内容链接。</p>'}`);
 }
 if(key==='quality'){
  desc='辅助维护视图，不占主导航；区分不同数据来源的结构与质量信息。';
  body=block('质量与结构',`<p>展示主数据库结构、V2 结构验收与来源覆盖。示例不执行任何实际检测。</p>${link('cases','返回案例库')}`);
 }
 if(['ai-annotation','v2-acceptance'].includes(key)){
  const target=key==='ai-annotation'?'annotation-workbench':'v2-database';
  desc='旧地址兼容入口，不是独立功能页面。';body=block('此入口已合并',link(target,'进入现行页面'));
 }
 const all=proposed?['index','audit','cases','case','terms','term','corpus','knowledge','quality']:Object.keys(names).filter(k=>!['cases','terms','audit','quality','map'].includes(k));
 const counterpart={database:'cases',annotation:'cases','v2-database':'cases','annotation-workbench':'audit','ai-annotation':'audit','v2-acceptance':'quality',cases:'database',terms:'database',audit:'annotation-workbench',quality:'v2-database'};
 return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${titles(mode,key)} · ${proposed?'建议':'当前'}架构演示</title><link rel="stylesheet" href="/style.css"></head><body data-mode="${mode}" data-page="${key}"><div class="demo-bar"><a href="/compare.html">左右同屏对比关系图</a><span>${proposed?'B · 建议架构':'A · 当前架构'} / 模拟数据</span><a href="/${proposed?'current':'proposed'}/${counterpart[key]||key}.html">切换到${proposed?'当前':'建议'}版对应页 ↗</a></div><header><a class="brand" href="/${mode}/index.html">高邮二王 <small>研究工作空间</small></a><nav aria-label="全站导航">${nav.map(k=>`<a ${k===key?'aria-current="page"':''} href="/${mode}/${k}.html">${titles(mode,k)}</a>`).join('')}</nav></header><main><div class="eyebrow">${proposed?'建议架构 / 以研究任务组织':'当前架构 / 按现有页面与链接组织'}</div><h1>${titles(mode,key)}</h1><p class="lead">${desc}</p>${key!=='map'?architecture.panel(mode,key):'<p class="map-return"><a href="/'+mode+'/index.html">← 本版本首页</a> · 此图是演示辅助页，不参与首页路径计算。</p>'}<div class="journey"><button id="back">← 返回刚才的位置</button><span id="trail"></span><button id="reset-trail">重置体验路径</button></div>${body}<details class="inventory"><summary>演示工具：查看本版本全部页面（不属于网站导航）</summary><div class="actions">${all.map(k=>link(k)).join('')}</div></details></main><footer>页面用途与跳转关系原型 · 不连接真实数据库 · 不调用 AI · 审校示例仅保存在本浏览器</footer><script src="/client.js"></script></body></html>`;
}
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(['/style.css','/client.js'].includes(url.pathname)){res.setHeader('Content-Type',url.pathname.endsWith('css')?'text/css; charset=utf-8':'text/javascript; charset=utf-8');return res.end(fs.readFileSync(path.join(__dirname,url.pathname.slice(1))));}
 res.setHeader('Content-Type','text/html; charset=utf-8');
 if(url.pathname==='/compare.html')return res.end(comparison.page());
 if(url.pathname==='/')return res.end(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/style.css"><title>网站架构对照</title><main><div class="eyebrow">高邮二王 / 页面架构演示</div><h1>同一项工作，两种访问路径。</h1><p class="lead">从首页进入，也可以直接体验释证审校。所有页面都有用途说明和真实可点击的页面关系。</p><p><a class="action" href="/compare.html">左右同屏对比跳转关系 →</a></p><div class="compare"><section class="block"><span class="tag">A · 现状还原</span><h2>当前架构</h2><p>主数据库、人工标注库、V2 工作库分别浏览；保留现有全站五步释证入口。</p><a class="action" href="/current/index.html">打开当前版首页 ↗</a><a class="action" href="/current/map.html">当前版完整跳转图 ↗</a><a class="action" href="/current/annotation-workbench.html">直接体验当前五步释证 ↗</a></section><section class="block"><span class="tag">B · 建议方案</span><h2>工作优先，材料互通</h2><p>释证与审校成为突出入口；案例集中浏览，多处可直接开始审校，材料之间携带对象跳转。</p><a class="action" href="/proposed/index.html">打开建议版首页 ↗</a><a class="action" href="/proposed/map.html">建议版完整跳转图 ↗</a><a class="action" href="/proposed/audit.html">直接体验建议审校工作台 ↗</a></section></div><section class="block"><h2>建议这样比较</h2><p>① 从首页开始审校　② 从案例列表开始审校　③ 从原典找到案例并开始审校　④ 审校中查原文后返回。</p><p>用同一浏览器的两个标签页分别打开 A / B。页顶可以切换对应页面；底部页面清单是演示辅助工具。两版的审校草稿分别保存，互不影响。</p></section></main></html>`);
 const m=url.pathname.match(/^\/(current|proposed)\/([a-z0-9-]+)\.html$/);
 if(!m||!names[m[2]]){res.statusCode=404;return res.end('页面不存在');}
 if(m[1]==='current'&&['ai-annotation','v2-acceptance'].includes(m[2])){res.statusCode=302;res.setHeader('Location',`/current/${m[2]==='ai-annotation'?'annotation-workbench.html':`v2-database.html${url.search}#browse`}`);return res.end();}
 res.end(render(m[1],m[2],url));
});
server.listen(port,'127.0.0.1',()=>console.log(`Architecture demos: http://127.0.0.1:${port}`));

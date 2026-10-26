const architecture=require('./architecture');
const mapping={database:['terms','cases'],annotation:['cases'],'v2-database':['cases'],'annotation-workbench':['audit'],'ai-annotation':['audit'],'v2-acceptance':['quality']};
const mapped=k=>mapping[k]||[k];
const current=architecture.edges('current').filter(e=>e.type==='content');
const proposed=architecture.edges('proposed').filter(e=>e.type==='content');
function equivalent(old,next){return mapped(old.from).includes(next.from)&&mapped(old.to).includes(next.to);}
function graph(mode){
 let svg=architecture.diagram(mode).match(/<svg[\s\S]*?<\/svg>/)[0];
 svg=svg.replace('id="architecture-graph"',`id="graph-${mode}" class="compare-graph"`);
 const positions=mode==='current'?{index:[200,25],database:[35,155],annotation:[355,155],'v2-database':[35,335],corpus:[355,335],term:[35,515],case:[355,515],'annotation-workbench':[35,695],knowledge:[355,695],'ai-annotation':[35,875],'v2-acceptance':[355,875]}:{index:[200,25],terms:[35,155],cases:[355,155],audit:[35,335],corpus:[355,335],term:[35,515],case:[355,515],quality:[35,695],knowledge:[355,695]};
 svg=svg.replace('viewBox="0 0 1150 690"','viewBox="0 0 600 985"');
 svg=svg.replace(/(<path class="edge [^"]+" data-from="([^"]+)" data-to="([^"]+)" )d="[^"]+"/g,(all,prefix,from,to)=>{const [x,y]=positions[from],[tx,ty]=positions[to],dx=tx-x,dy=ty-y,scale=Math.max(Math.abs(dx)/110,Math.abs(dy)/43);return `${prefix}d="M ${x+105+dx/scale} ${y+39+dy/scale} Q ${(x+tx)/2+105+(x===tx?65:0)} ${(y+ty)/2+39+(y===ty?-60:0)} ${tx+105-dx/scale} ${ty+39-dy/scale}"`;});
 svg=svg.replace(/<a href="([^"]+)" class="graph-node ([^"]*)">[\s\S]*?<\/a>/g,(all,href)=>{const key=href.split('/').pop().split('.html')[0],[x,y]=positions[key];let textIndex=0;return all.replace(/<rect x="[^"]+" y="[^"]+"/,`<rect x="${x}" y="${y}"`).replace(/(<text[^>]*?) x="[^"]+" y="[^"]+"/g,(_,prefix)=>`${prefix} x="${x+105}" y="${y+(textIndex++?56:31)}"`);});
 svg=svg.replaceAll('arrow-',`${mode}-arrow-`);
 svg=svg.replace(/<path class="edge ([^"]+)" data-from="([^"]+)" data-to="([^"]+)"([^>]+)>/g,(all,type,from,to,tail)=>{
  let state='same';
  if(type==='redirect')state='legacy';
  if(type==='content')state=mode==='current'?(proposed.some(e=>equivalent({from,to},e))?'same':'removed'):(current.some(e=>equivalent(e,{from,to}))?'same':'added');
  const color={same:'#94a397',removed:'#c26928',added:'#087b64',legacy:'#8b8291'}[state];
  return `<path class="edge ${type} ${state}" data-from="${from}" data-to="${to}"${tail.replace(/marker-end="[^"]+"/,`marker-end="url(#${mode}-diff-${state})"`)}><title>${state==='added'?'新增内容跳转':state==='removed'?'旧跳转由新组织替代':'保留或对应关系'}</title>`;
 });
 svg=svg.replace('</svg>',`${['same','removed','added','legacy'].map(s=>`<defs><marker id="${mode}-diff-${s}" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="${{same:'#94a397',removed:'#c26928',added:'#087b64',legacy:'#8b8291'}[s]}"/></marker></defs>`).join('')}</svg>`);
 const reorganized=mode==='current'?['database','annotation','v2-database','case']:['cases','case'];
 svg=svg.replace(/<a href="([^"]+)" class="graph-node ([^"]*)">/g,(all,href,cls)=>{const key=href.split('/').pop().split('.html')[0];return `<a href="${href}" target="_blank" rel="noopener" class="graph-node ${cls} ${reorganized.includes(key)?'reorganized':''}">`;});
 return svg;
}
function page(){
 const lower=architecture.diagram('proposed');
 const tables=lower.slice(lower.indexOf('<section class="block"><h2>哪些页面合并了？'));
 return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>当前与建议架构 · 左右对比</title><link rel="stylesheet" href="/style.css"></head><body class="comparison-page"><div class="demo-bar"><a href="/">返回演示首页</a><span>页面架构 / 同屏对照</span><a href="/proposed/index.html">体验建议版 ↗</a></div><main><div class="eyebrow">A / B · 可点击关系图</div><h1>当前在左，建议在右。</h1><p class="lead">紫色看页面合并，绿色看新增捷径，橙色看被新组织替代的旧跳转。点击节点在新标签页打开，保留对照视图。</p><div class="diff-legend"><span class="purple">■ 紫色节点：参与合并的页面</span><span class="green">━ 绿色实线：新增内容跳转</span><span class="orange">┄ 橙色虚线：被替代的旧跳转</span><span class="gray">━ 灰线：保留 / 重命名后的对应跳转</span></div><div class="compare-controls"><label><input id="diff-only" type="checkbox"> 只突出变化</label><label><input id="compare-nav" type="checkbox"> 显示全站导航线</label><label>任务对照 <select id="compare-task"><option value="all">全部关系</option><option value="corpus">原典关联案例 → 审校：2 步变 1 步</option><option value="home">首页 → 审校：仍是 1 步</option></select></label></div><p id="task-caption" role="status">旧页面身份先按“主库→字词库/案例库、人工库/V2列表→案例库、五步释证→释证与审校”对应后，再比较内容连线；橙线不表示相应能力被删除。</p><div class="pair-scroll"><div class="graph-pair"><section><div class="pair-heading"><h2>A · 当前架构</h2><a href="/current/map.html" target="_blank">单独查看 ↗</a></div><p class="merge-note">紫色：主库案例、人工标注、V2 案例列表及原案例详情。</p>${graph('current')}<div class="nav-rule">全站入口：首页 / 主数据库 / 人工标注库 / 通用语料库 / V2 工作库 / 五步释证 / 训诂知识</div></section><section><div class="pair-heading"><h2>B · 建议架构</h2><a href="/proposed/map.html" target="_blank">单独查看 ↗</a></div><p class="merge-note">紫色：统一案例库 + 统一案例详情。主库字词另设字词库。</p>${graph('proposed')}<div class="nav-rule">全站入口：首页 / 释证与审校 / 案例库 / 字词库 / 原典检索 / 训诂知识</div></section></div></div><p>节点下方仍显示从首页的最少跨页次数。旧地址兼容入口保留；导航线默认折叠，避免遮挡任务关系。窄窗口可横向滚动整组图。</p>${tables}</main><script>
const diff=document.getElementById('diff-only'),nav=document.getElementById('compare-nav'),task=document.getElementById('compare-task');
function update(){document.querySelectorAll('.compare-graph').forEach(svg=>{svg.classList.toggle('show-nav',nav.checked);const mode=svg.id.endsWith('current')?'current':'proposed';svg.querySelectorAll('.edge').forEach(e=>{let fade=diff.checked&&e.classList.contains('same');if(task.value!=='all'){const pairs=task.value==='corpus'?(mode==='current'?['corpus>v2-database','v2-database>annotation-workbench']:['corpus>audit']):(mode==='current'?['index>annotation-workbench']:['index>audit']);fade=e.classList.contains('nav')||!pairs.includes(e.dataset.from+'>'+e.dataset.to);}e.classList.toggle('compare-faded',fade);});});document.getElementById('task-caption').textContent=task.value==='corpus'?'左：原典 → V2 案例 → 五步释证；右：原典 → 当前案例审校。减少 1 次跨页，限已有可靠审校映射的案例。':task.value==='home'?'两版从首页进入审校入口均为 1 次跨页；建议版改善入口突出程度，不夸大路径缩短。':'橙色表示旧页面组织下的跳转被替代，不代表删除对应功能。页面重命名和合并映射已计入比较。';}
diff.onchange=update;nav.onchange=update;task.onchange=update;
</script></body></html>`;
}
module.exports={page};

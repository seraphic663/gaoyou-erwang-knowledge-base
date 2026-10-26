const mode=document.body.dataset.mode;
const graph=document.getElementById('architecture-graph');
if(graph){const navToggle=document.getElementById('show-nav'),focus=document.getElementById('focus-page');const updateGraph=()=>{graph.classList.toggle('show-nav',navToggle.checked);graph.querySelectorAll('.edge').forEach(edge=>edge.classList.toggle('dimmed',Boolean(focus.value)&&edge.dataset.from!==focus.value&&edge.dataset.to!==focus.value));};navToggle.onchange=updateGraph;focus.onchange=updateGraph;}
const storageKey=`architecture-demo:${mode}:audit`;
const pathKey=`architecture-demo:${mode}:trail`;
const trail=JSON.parse(sessionStorage.getItem(pathKey)||'[]');
if(trail.at(-1)?.url!==location.pathname+location.search){trail.push({url:location.pathname+location.search,title:document.querySelector('h1').textContent});sessionStorage.setItem(pathKey,JSON.stringify(trail));}
document.getElementById('trail').textContent=`本次体验 ${Math.max(0,trail.length-1)} 次跨页 · ${trail.slice(-4).map(x=>x.title).join(' → ')}`;
document.getElementById('back').onclick=()=>{if(trail.length>1){trail.pop();const target=trail.pop();sessionStorage.setItem(pathKey,JSON.stringify(trail));location.href=target.url;}else location.href=`/${mode}/index.html`;};
document.getElementById('reset-trail').onclick=()=>{sessionStorage.removeItem(pathKey);location.reload();};
const filter=document.getElementById('source-filter');
if(filter){filter.value=new URLSearchParams(location.search).get('source')||'all';const update=()=>{document.querySelectorAll('[data-source]').forEach(el=>el.hidden=filter.value!=='all'&&el.dataset.source!==filter.value);const u=new URL(location.href);u.searchParams.set('source',filter.value);history.replaceState(null,'',u);};filter.onchange=update;update();}
const workspace=document.getElementById('workspace');
if(workspace){
 let state=JSON.parse(localStorage.getItem(storageKey)||'{"generated":false,"steps":{},"notes":{},"history":[]}');
 const save=()=>localStorage.setItem(storageKey,JSON.stringify(state));
 const render=()=>{
  if(!state.generated)return;
  document.getElementById('draft').innerHTML=['发疑','设问','取证','释理','结论'].map((name,i)=>`<div class="audit-step"><h3>${i+1}. ${name}</h3><p>模拟草稿：依据当前案例材料整理“${name}”。这段文字用于体验审校流程。</p>${['认可','修改','存疑'].map(v=>`<label><input type="radio" name="step-${i}" data-step="${i}" value="${v}" ${state.steps[i]===v?'checked':''}>${v}</label>`).join('')}<textarea data-note="${i}" placeholder="本步意见（离开页面后仍保留）"></textarea></div>`).join('')+'<button id="save-audit">模拟保存本次审核</button><div id="history"></div>';
  document.querySelectorAll('[data-note]').forEach(el=>{el.value=state.notes[el.dataset.note]||'';el.oninput=()=>{state.notes[el.dataset.note]=el.value;save();};});
  document.querySelectorAll('[data-step]').forEach(el=>el.onchange=()=>{state.steps[el.dataset.step]=el.value;save();});
  const history=()=>document.getElementById('history').textContent=`本地模拟历史：${state.history.length} 次${state.history.length?' · 最近 '+state.history.at(-1).time:''}`;
  document.getElementById('save-audit').onclick=()=>{if(Object.keys(state.steps).length<5){document.getElementById('save-state').textContent='请先为五个步骤分别选择审核意见。';return;}state.history.push({time:new Date().toLocaleString('zh-CN'),steps:{...state.steps},notes:{...state.notes}});save();history();document.getElementById('save-state').textContent='已保存到本浏览器演示记录，未写入真实数据库。';};history();
 };
 document.getElementById('choose-case').onclick=()=>{workspace.hidden=false;const u=new URL(location.href);u.searchParams.set('case',mode==='proposed'?'demo-zaozhou':'v2-demo-zaozhou');history.replaceState(null,'',u);trail[trail.length-1].url=u.pathname+u.search;sessionStorage.setItem(pathKey,JSON.stringify(trail));render();workspace.scrollIntoView({behavior:'smooth'});};
 document.getElementById('generate').onclick=()=>{state.generated=true;save();render();};
 if(!workspace.hidden)render();
}

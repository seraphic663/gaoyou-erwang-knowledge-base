const PAGES = Object.freeze({
  '/': 'index.html', '/cases': 'cases.html', '/case': 'case.html',
  '/terms': 'terms.html', '/term': 'term.html', '/audit': 'audit.html',
  '/corpus': 'corpus.html', '/knowledge': 'knowledge.html', '/quality': 'quality.html',
});
function resolvePage(url) {
  let pathname = url.pathname.replace(/^\/web(?=\/)/, '');
  const q = new URLSearchParams(url.search);
  let target;
  if (pathname === '/index.html') target = '/';
  if (pathname === '/database.html') {
    target = q.get('view') === 'schema' ? '/quality' : q.get('view') === 'cases' ? '/cases' : '/terms';
    if (target === '/cases') q.set('source', 'main');
    if (target === '/quality') q.set('view', 'schema'); else q.delete('view');
  }
  if (pathname === '/annotation.html') { target = '/cases'; q.set('source', 'annotation'); }
  if (pathname === '/v2-database.html' || pathname === '/v2-acceptance.html') {
    target = q.has('case') ? '/case' : '/cases'; q.set('source', 'v2');
    if (q.has('case')) { q.set('id', q.get('case')); q.delete('case'); }
  }
  if (pathname === '/annotation-workbench.html' || pathname === '/ai-annotation.html') target = '/audit';
  for (const key of ['case', 'term', 'corpus', 'knowledge', 'cases', 'terms', 'audit', 'quality']) {
    if (pathname === '/' + key + '.html') target = '/' + key;
  }
  if (target === '/case' && !q.has('source')) q.set('source', 'main');
  if (!target && pathname.endsWith('/') && pathname !== '/' && PAGES[pathname.slice(0, -1)]) target = pathname.slice(0, -1);
  if (target) return { redirect: target + (q.size ? '?' + q.toString() : '') };
  return PAGES[pathname] ? { file: PAGES[pathname] } : null;
}
module.exports = { PAGES, resolvePage };

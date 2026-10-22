window.Site = (() => {
  const params = new URLSearchParams(location.search);
  const url = (path, query = {}) => path + (Object.keys(query).length ? '?' + new URLSearchParams(query) : '');
  const safeReturn = (value) => {
    try { const u = new URL(value, location.origin); return u.origin === location.origin && ['/', '/cases', '/terms', '/case', '/term', '/audit', '/corpus', '/knowledge', '/quality'].includes(u.pathname) ? u.pathname + u.search + u.hash : null; } catch { return null; }
  };
  const current = () => location.pathname + location.search;
  const caseUrl = (source, id) => url('/case', { source, id, return: current() });
  const auditUrl = (id) => url('/audit', { case: id, return: current() });
  const link = (href, text) => '<a class="detail-link" href="' + escapeHtml(href) + '">' + escapeHtml(text) + '</a>';
  const back = document.querySelector('#siteBack');
  if (back) { back.href = safeReturn(params.get('return')) || '/cases'; back.textContent = params.has('return') ? '返回来时位置' : '返回案例库'; }
  async function auditLinks(source, ids) {
    const q = new URLSearchParams({ source }); ids.forEach(id => q.append('id', id));
    return (await requestJson('/api/site/audit-targets?' + q)).targets;
  }
  const auditMarkup = (ids) => !ids?.length ? '<span class="compact-note">尚无已核实的 V2 对应关系</span>' : ids.map((id, i) => link(auditUrl(id), ids.length === 1 ? '开始释证与审校' : '审校对应记录 ' + (i + 1))).join(' ');
  document.querySelectorAll('.nav-links a').forEach(a => { if (new URL(a.href).pathname === location.pathname) a.setAttribute('aria-current', 'page'); });
  return { url, safeReturn, current, caseUrl, auditUrl, link, auditLinks, auditMarkup };
})();

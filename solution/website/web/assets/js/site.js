window.Site = (() => {
  const params = new URLSearchParams(location.search);

  function url(path, query = {}) {
    const search = new URLSearchParams(query).toString();
    return path + (search ? '?' + search : '');
  }

  function safeReturn(value) {
    if (!value) return null;
    try {
      const target = new URL(value, location.origin);
      const knownPage = PageCatalog.some(page => page.path === target.pathname);
      return target.origin === location.origin && knownPage
        ? target.pathname + target.search + target.hash
        : null;
    } catch {
      return null;
    }
  }

  const current = () => location.pathname + location.search;
  const caseUrl = (source, id) => url('/case', { source, id, return: current() });
  const auditUrl = id => url('/audit', { case: id, return: current() });
  const link = (href, text) => `<a class="detail-link" href="${escapeHtml(href)}">${escapeHtml(text)}</a>`;

  function options(values) {
    return values.map(option => `
      <option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>
    `).join('');
  }

  function pagination(path, params, page, pages, pageKey = 'page') {
    const adjacent = [
      page > 1 ? { page: page - 1, label: '上一页' } : null,
      page < pages ? { page: page + 1, label: '下一页' } : null,
    ].filter(Boolean);
    const links = adjacent.map(target => {
      const search = new URLSearchParams(params);
      search.set(pageKey, target.page);
      return link(path + '?' + search, target.label);
    });
    return `<div class="site-actions">${links.join('')}<span>第 ${page} / ${pages} 页</span></div>`;
  }

  async function auditLinks(source, ids) {
    const query = new URLSearchParams({ source });
    ids.forEach(id => query.append('id', id));
    return (await requestJson('/api/site/audit-targets?' + query)).targets;
  }

  function auditMarkup(ids) {
    if (!ids?.length) return '<span class="compact-note">尚无已核实的 V2 对应关系</span>';
    return ids.map((id, index) => link(
      auditUrl(id),
      ids.length === 1 ? '开始释证与审校' : `审校对应记录 ${index + 1}`,
    )).join(' ');
  }

  const back = document.querySelector('#siteBack');
  if (back) {
    const previous = safeReturn(params.get('return'));
    if (previous && previous !== current()) {
      back.href = previous;
      back.textContent = '返回来时位置';
      back.hidden = false;
    }
  }

  return { url, safeReturn, current, caseUrl, auditUrl, link, options, pagination, auditLinks, auditMarkup };
})();

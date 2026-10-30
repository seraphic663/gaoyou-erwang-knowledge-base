const PAGE_CATALOG = require('../web/assets/js/page-catalog');
const PAGES = Object.freeze(Object.fromEntries(PAGE_CATALOG.map(page => [page.path, page.file])));

function renderNavigation(activeUrl) {
  const url = typeof activeUrl === 'string' ? new URL(activeUrl, 'http://localhost') : activeUrl;
  const activePath = url.pathname;
  const annotationPage = ['/cases', '/case'].includes(activePath) && url.searchParams.get('source') === 'annotation';
  const links = PAGE_CATALOG.filter(page => page.navigation).map(page => {
    const selected = page.path === '/cases'
      ? annotationPage
      : !annotationPage && (page.path === activePath || page.activePaths?.includes(activePath));
    const active = selected ? ' aria-current="page"' : '';
    return `<a href="${page.href || page.path}"${active}>${page.label}</a>`;
  });
  return `<nav class="nav" aria-label="主导航">
    <a class="brand" href="/">高邮二王知识库</a>
    <div class="nav-links">${links.join('')}</div>
  </nav>`;
}

function resolvePage(url) {
  if (url.pathname === '/library' || url.pathname === '/terms') {
    return { file: 'machine-library.html' };
  }
  if (url.pathname === '/cases' && (!url.searchParams.get('source') || ['parser', 'main', 'all'].includes(url.searchParams.get('source')))) {
    return { file: 'machine-library.html' };
  }
  return Object.hasOwn(PAGES, url.pathname) ? { file: PAGES[url.pathname] } : null;
}

module.exports = { PAGES, resolvePage, renderNavigation };

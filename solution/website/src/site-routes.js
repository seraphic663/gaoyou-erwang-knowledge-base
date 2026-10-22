const PAGE_CATALOG = require('../web/assets/js/page-catalog');
const PAGES = Object.freeze(Object.fromEntries(PAGE_CATALOG.map(page => [page.path, page.file])));

function renderNavigation(activePath) {
  const links = PAGE_CATALOG.filter(page => page.navigation).map(page => {
    const active = page.path === activePath ? ' aria-current="page"' : '';
    return `<a href="${page.path}"${active}>${page.label}</a>`;
  });
  return `<nav class="nav" aria-label="主导航">
    <a class="brand" href="/">高邮二王知识库</a>
    <div class="nav-links">${links.join('')}</div>
  </nav>`;
}

function resolvePage(url) {
  return Object.hasOwn(PAGES, url.pathname) ? { file: PAGES[url.pathname] } : null;
}

module.exports = { PAGES, resolvePage, renderNavigation };

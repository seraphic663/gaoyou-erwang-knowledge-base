/* One page catalog for server routing and browser navigation. */
(function (root) {
  const pages = [
    { path: '/', file: 'index.html', label: '首页', navigation: true },
    { path: '/audit', file: 'audit.html', label: '案例审校', navigation: true },
    { path: '/cases', file: 'cases.html', label: '案例库', navigation: true },
    { path: '/terms', file: 'terms.html', label: '字词库', navigation: true },
    { path: '/corpus', file: 'corpus.html', label: '典籍检索', navigation: true },
    { path: '/reading-lab', file: 'reading-lab.html', label: '校读实验', navigation: true },
    { path: '/knowledge', file: 'knowledge.html', label: '训诂知识', navigation: true },
    { path: '/case', file: 'case.html', label: '案例详情' },
    { path: '/term', file: 'term.html', label: '字词详情' },
    { path: '/quality', file: 'quality.html', label: '质量报告' },
  ];
  const catalog = Object.freeze(pages.map(Object.freeze));
  if (typeof module !== 'undefined' && module.exports) module.exports = catalog;
  else root.PageCatalog = catalog;
})(typeof window === 'undefined' ? globalThis : window);

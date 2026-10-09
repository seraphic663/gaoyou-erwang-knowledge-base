const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const WEB_DIR = path.join(__dirname, '..', 'web');
const PAGE_FILES = [
  'index.html',
  'database.html',
  'annotation.html',
  'corpus.html',
  'v2-database.html',
  'ai-annotation.html',
  'annotation-workbench.html',
  'knowledge.html',
  'term.html',
  'case.html',
];
const REQUIRED_NAV_HREFS = [
  './index.html',
  './database.html?view=terms',
  './annotation.html',
  './corpus.html',
  './v2-database.html#browse',
  './annotation-workbench.html',
  './knowledge.html',
];

function navBlock(file) {
  const html = fs.readFileSync(path.join(WEB_DIR, file), 'utf8');
  const match = html.match(/<nav class="nav"[^>]*>[\s\S]*?<\/nav>/);
  assert.ok(match, `${file} must contain the shared main navigation`);
  return match[0];
}

test('all user-facing pages expose the same main navigation routes', () => {
  const signatures = PAGE_FILES.map((file) => {
    const nav = navBlock(file);
    assert.match(nav, /aria-label="主导航"/);
    for (const href of REQUIRED_NAV_HREFS) {
      assert.match(nav, new RegExp(`href="${href.replace(/[.?]/g, '\\$&')}`), `${file} is missing ${href}`);
    }
    assert.doesNotMatch(nav, /ai-annotation\.html/);
    assert.doesNotMatch(nav, /实验性功能|annotation-workbench\.js/);
    return REQUIRED_NAV_HREFS.map((href) => nav.includes(`href="${href}"`)).join('');
  });
  assert.equal(new Set(signatures).size, 1);
});

test('the retired V2 entry redirects into the unified workspace', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'v2-acceptance.html'), 'utf8');
  assert.match(html, /v2-database\.html/);
  assert.match(html, /window\.location\.replace/);
  assert.match(html, /#browse/);
});

test('V2 case browsing keeps retired migration submissions out of the user path', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'v2-database.html'), 'utf8');
  const script = fs.readFileSync(path.join(WEB_DIR, 'assets/js/v2-acceptance.js'), 'utf8');
  assert.doesNotMatch(html, /v2ReviewTab|v2ReviewWorkspace|待办审校/);
  assert.doesNotMatch(html, /v2PassageSearch|v2-passage-search/);
  assert.match(html, /仅检索当前 V2 案例库/);
  assert.match(html, /id="v2CaseSearch"[^>]*placeholder="标题、来源、目标典籍"/);
  assert.doesNotMatch(script, /\/api\/v2\/retrieve/);
  assert.match(script, /requestedMode === 'review'/);
  assert.match(script, /annotation-workbench\.html\?case=/);
  assert.match(script, /v2-case-row-action/);
});

test('generic corpus search is independent from the V2 workspace', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'corpus.html'), 'utf8');
  const script = fs.readFileSync(path.join(WEB_DIR, 'assets/js/corpus-browser.js'), 'utf8');
  assert.match(html, /通用语料库/);
  assert.match(html, /corpusSearchForm/);
  assert.match(html, /assets\/js\/corpus-browser\.js/);
  assert.match(script, /\/api\/corpus\/retrieve/);
  assert.doesNotMatch(script, /\/api\/v2\/retrieve/);
  assert.doesNotMatch(script, /\/api\/v2\/retrieve/);
});

test('five-step review uses progressive disclosure with evidence on the right', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'annotation-workbench.html'), 'utf8');
  const script = fs.readFileSync(path.join(WEB_DIR, 'assets/js/five-step-audit.js'), 'utf8');
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/five-step-audit.css'), 'utf8');
  assert.match(html, /data-five-step-view-mode="simple"/);
  assert.match(html, /data-five-step-view-mode="detailed"/);
  assert.match(html, /fiveStepEvidenceOverview/);
  assert.match(html, /fiveStepWriteArm/);
  assert.match(html, /<option value="reviewed">认可<\/option>/);
  assert.match(html, /<option value="needs_revision">修改<\/option>/);
  assert.match(html, /<option value="uncertain">存疑<\/option>/);
  assert.match(html, /aria-label="发疑、设问、取证、释理、结论"/);
  assert.match(script, /five-step-evidence-panel/);
  assert.match(script, /renderMarkdownLite/);
  assert.match(script, /label: '发疑'/);
  assert.match(script, /label: '释理'/);
  assert.doesNotMatch(script, /five-step-step-nav-status/);
  assert.match(script, /认可/);
  assert.match(script, /review_view_mode/);
  assert.match(css, /\.five-step-audit-page\[data-view-mode="simple"\] \.five-step-engineering-detail/);
  assert.match(css, /\.five-step-step-nav\s*\{[\s\S]*display:\s*flex/);
  assert.match(html, /assets\/js\/five-step-audit\.js\?v=v8/);
});

test('the retired freeform AI entry redirects into the unified five-step workspace', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'ai-annotation.html'), 'utf8');
  assert.match(html, /annotation-workbench\.html/);
  assert.match(html, /window\.location\.replace/);
});

test('five-step route provides an in-page case chooser without requiring the full V2 list', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'annotation-workbench.html'), 'utf8');
  const script = fs.readFileSync(path.join(WEB_DIR, 'assets/js/five-step-audit.js'), 'utf8');
  assert.match(html, /fiveStepRecommended/);
  assert.match(html, /fiveStepCaseSearch/);
  assert.match(html, /查看完整 V2 案例库与质量报告/);
  assert.match(script, /loadCaseChooser/);
  assert.match(script, /\/api\/v2\/cases\?/);
});

test('annotation browser exposes aligned annotator and origin filters', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'annotation.html'), 'utf8');
  const script = fs.readFileSync(path.join(WEB_DIR, 'assets/js/annotation.js'), 'utf8');
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/styles.css'), 'utf8');
  assert.match(html, /id="annotationAnnotatorFilters"/);
  assert.match(html, /id="annotationOriginFilters"/);
  assert.match(html, /id="annotationQuickSearches"/);
  assert.doesNotMatch(html, /annotationResetButton|annotationPresets/);
  assert.match(html, /annotation\.js\?v=annotation-search-v5/);
  assert.match(script, /new Set\(state\.annotators\)/);
  assert.match(script, /new Set\(state\.origins\)/);
  assert.match(script, /QUICK_SEARCHES/);
  assert.match(script, /data-annotation-quick-query/);
  assert.match(script, /薄言有之/);
  assert.match(script, /data-annotation-annotator/);
  assert.match(script, /data-annotation-origin/);
  assert.match(script, /\/api\/annotation\/index/);
  assert.match(script, /\/api\/annotation\/detail\?id=/);
  assert.match(script, /search-hit/);
  assert.match(html, /<h4>标注者<\/h4>/);
  assert.match(html, /<h4>出处<\/h4>/);
  assert.match(css, /\.annotation-filter-option\s*\{/);
  assert.match(css, /\.annotation-quick-searches\s*\{/);
  assert.match(css, /\.annotation-browser-layout\s*\{[\s\S]*align-items:\s*start/);
  assert.match(css, /\.annotation-browser-layout \.browser-main\s*\{[\s\S]*align-content:\s*start/);
  assert.match(css, /\.annotation-origin-group\s*\{/);
  assert.match(script, /annotation-target-card/);
  assert.doesNotMatch(script, /<strong>出处<\/strong>|<strong>标注者<\/strong>|<strong>状态<\/strong>/);
  assert.match(css, /\.annotation-target-card\s*\{/);
  assert.doesNotMatch(css, /\.annotation-raw-grid\s*\{[\s\S]*repeat\(4/);
});

test('main navigation stays in the hero flow and keeps its brand on one line', () => {
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/styles.css'), 'utf8');
  assert.match(css, /\.nav\s*\{[\s\S]*position:\s*relative/);
  assert.match(css, /\.nav\s*\{[\s\S]*max-width:\s*1100px/);
  assert.match(css, /\.brand\s*\{[\s\S]*white-space:\s*nowrap/);
  assert.match(css, /\.nav-links\s*\{[\s\S]*position:\s*static/);
});

test('shared hero surfaces keep navigation overlays unclipped', () => {
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/styles.css'), 'utf8');
  const heroSurfaceRule = [...css.matchAll(/\.hero,\s*\.subhero\s*\{([\s\S]*?)\n\}/g)]
    .find((match) => /position:\s*relative/.test(match[1]) && /overflow:\s*visible/.test(match[1]));
  assert.ok(heroSurfaceRule, 'styles.css must define one shared hero surface rule');
  assert.match(heroSurfaceRule[1], /position:\s*relative/);
  assert.match(heroSurfaceRule[1], /overflow:\s*visible/);
  for (const file of PAGE_FILES) {
    const html = fs.readFileSync(path.join(WEB_DIR, file), 'utf8');
    assert.match(html, /class="database-panel"/, `${file} must expose the shared navigation overlay`);
  }
});

test('redundant hero summary panels are removed from the user-facing pages', () => {
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/styles.css'), 'utf8');
  assert.doesNotMatch(css, /\.hero-panel(?:-item)?\s*\{/);
  for (const file of PAGE_FILES) {
    const html = fs.readFileSync(path.join(WEB_DIR, file), 'utf8');
    assert.doesNotMatch(html, /class="hero-panel(?:\s|[^"])*"/, `${file} must not render the deleted summary panel`);
  }

  const scriptFiles = [
    'assets/js/browser-common.js',
    'assets/js/browser.js',
    'assets/js/annotation.js',
    'assets/js/detail.js',
    'assets/js/v2-acceptance.js',
  ];
  for (const file of scriptFiles) {
    const script = fs.readFileSync(path.join(WEB_DIR, file), 'utf8');
    assert.doesNotMatch(script, /renderHeroItems|renderHeroMeta|renderMetaCards|HeroMeta|detailMeta/);
  }
});

test('tablet and mobile hero layouts stay compact instead of forcing avoidable wrapping', () => {
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/styles.css'), 'utf8');
  assert.doesNotMatch(
    css,
    /@media\s*\(max-width:\s*900px\)[\s\S]*?\.hero-panel\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2/,
    'the 900px breakpoint must not force the hero stats into two rows',
  );
  assert.doesNotMatch(css, /@media\s*\(max-width:\s*700px\)[\s\S]*?\.hero-panel\s*\{/);
  assert.match(
    css,
    /@media\s*\(max-width:\s*700px\)[\s\S]*?\.nav-links\s*\{[\s\S]*?flex-wrap:\s*nowrap[\s\S]*?overflow:\s*visible/,
    'mobile navigation must stay on one compact row without clipping overlays',
  );
  assert.match(
    css,
    /@media\s*\(max-width:\s*700px\)[\s\S]*?\.database-menu,\s*\.database-trigger\s*\{[\s\S]*?width:\s*auto/,
    'the database menu must not consume a full mobile row',
  );
});

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const WEB_DIR = path.join(__dirname, '..', 'web');
const PAGE_FILES = [
  'index.html',
  'database.html',
  'annotation.html',
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
  assert.match(script, /requestedMode === 'review'/);
  assert.match(script, /annotation-workbench\.html\?case=/);
  assert.match(script, /v2-case-row-action/);
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
  assert.match(html, /id="annotationAnnotatorFilter"/);
  assert.match(html, /id="annotationOriginFilter"/);
  assert.match(html, /annotation\.js\?v=annotation-filters-v1/);
  assert.match(script, /annotator: state\.annotator/);
  assert.match(script, /origin: state\.origin/);
  assert.match(script, /标注者/);
  assert.match(script, /出处/);
  assert.match(css, /\.annotation-filter-grid\s*\{[\s\S]*grid-template-columns:/);
  assert.match(css, /\.annotation-raw-grid\s*\{[\s\S]*repeat\(4/);
});

test('main navigation stays in the hero flow and keeps its brand on one line', () => {
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/styles.css'), 'utf8');
  assert.match(css, /\.nav\s*\{[\s\S]*position:\s*relative/);
  assert.match(css, /\.nav\s*\{[\s\S]*max-width:\s*1100px/);
  assert.match(css, /\.brand\s*\{[\s\S]*white-space:\s*nowrap/);
  assert.match(css, /\.nav-links\s*\{[\s\S]*position:\s*static/);
});

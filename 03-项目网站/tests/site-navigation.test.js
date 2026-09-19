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
  './ai-annotation.html',
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
});

test('five-step review uses progressive disclosure with evidence on the right', () => {
  const html = fs.readFileSync(path.join(WEB_DIR, 'annotation-workbench.html'), 'utf8');
  const script = fs.readFileSync(path.join(WEB_DIR, 'assets/js/five-step-audit.js'), 'utf8');
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/five-step-audit.css'), 'utf8');
  assert.match(html, /data-five-step-view-mode="simple"/);
  assert.match(html, /data-five-step-view-mode="detailed"/);
  assert.match(html, /fiveStepEvidenceOverview/);
  assert.match(script, /five-step-evidence-panel/);
  assert.match(script, /认可 AI 草稿/);
  assert.match(script, /review_view_mode/);
  assert.match(css, /\.five-step-audit-page\[data-view-mode="simple"\] \.five-step-engineering-detail/);
});

test('main navigation is fixed at the upper right on desktop', () => {
  const css = fs.readFileSync(path.join(WEB_DIR, 'assets/css/styles.css'), 'utf8');
  assert.match(css, /\.nav-links\s*\{[\s\S]*position:\s*fixed/);
  assert.match(css, /\.nav-links\s*\{[\s\S]*top:\s*16px/);
  assert.match(css, /\.nav-links\s*\{[\s\S]*right:\s*24px/);
});

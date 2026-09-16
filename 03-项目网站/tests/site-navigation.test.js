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
});

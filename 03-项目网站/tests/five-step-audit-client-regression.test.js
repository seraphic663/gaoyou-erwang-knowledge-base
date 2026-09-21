const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const CLIENT_SOURCE = fs.readFileSync(
  path.join(__dirname, '..', 'web', 'assets', 'js', 'five-step-audit.js'),
  'utf8',
);

function runMalformedReviewState() {
  const start = CLIENT_SOURCE.indexOf('  function updateSaveButton()');
  const end = CLIENT_SOURCE.indexOf('\n  function renderHistory', start);
  assert.ok(start >= 0 && end > start, 'could not isolate updateSaveButton');
  const updateSaveButton = CLIENT_SOURCE.slice(start, end);
  const helperStart = CLIENT_SOURCE.indexOf('  function safeTrim(value)');
  const helperEnd = CLIENT_SOURCE.indexOf('\n\n  function renderInlineMarkdown', helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, 'could not isolate safeTrim');
  const safeTrim = CLIENT_SOURCE.slice(helperStart, helperEnd);
  const code = `
    const el = {
      reviewer: { value: undefined },
      save: { disabled: false },
      writeStatus: { textContent: '', classList: { add() {}, remove() {} } },
      writeArm: { disabled: false, checked: true },
    };
    const state = {
      reviewedSteps: Array.from({ length: 5 }, () => ({ status: 'accepted', text: undefined, comment: undefined })),
      writeEnabled: true,
      writeArmed: true,
      generation: {},
      saving: false,
    };
    const STEP_DEFINITIONS = Array.from({ length: 5 }, (_, index) => ({ field: String(index) }));
    function renderProgress() {}
    ${safeTrim}
    ${updateSaveButton}
    updateSaveButton();
  `;
  vm.runInNewContext(code, { console });
}

test('does not crash when a legacy review state has missing text fields', () => {
  assert.doesNotThrow(runMalformedReviewState);
});

test('does not leave naked trim calls in the five-step client', () => {
  const withoutSafeTrim = CLIENT_SOURCE.replace(
    /function safeTrim\(value\) \{[\s\S]*?\n  \}/,
    '',
  );
  assert.doesNotMatch(withoutSafeTrim, /\.trim\(\)/);
});

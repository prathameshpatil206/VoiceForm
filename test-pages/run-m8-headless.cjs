/**
 * run-m8-headless.js
 * M8 headless scanner compatibility test harness.
 *
 * Uses jsdom to load each Category A-F HTML test page and runs a self-contained
 * DOM scanner (mirroring the M1 TypeScript logic) to verify field detection
 * without requiring a Chrome extension host.
 *
 * Usage:
 *   node test-pages/run-m8-headless.js
 *
 * Output: JSON to stdout with per-category scan results.
 */

'use strict';

const { JSDOM } = require('jsdom');
const fs = require('fs');
const path = require('path');

const TEST_PAGES_DIR = path.resolve(__dirname);

// ──────────────────────────────────────────────────────────────────────────────
// Self-contained DOM scanner (mirrors M1 TypeScript logic, no chrome APIs)
// ──────────────────────────────────────────────────────────────────────────────

const IGNORED_TYPES = new Set(['submit', 'button', 'reset', 'image', 'hidden']);

/**
 * Resolve the human-readable label for a form control element.
 * Priority: label[for] → aria-labelledby → aria-label → title → placeholder → name
 */
function resolveLabel(el, document) {
  // 1. label[for=id]
  if (el.id) {
    const labelEl = document.querySelector(`label[for="${el.id}"]`);
    if (labelEl) {
      const text = labelEl.textContent.replace(/\s+/g, ' ').trim();
      if (text) return { label: text, method: 'label_for' };
    }
  }

  // 2. aria-labelledby
  const labelledBy = el.getAttribute('aria-labelledby');
  if (labelledBy) {
    const texts = labelledBy.trim().split(/\s+/)
      .map(id => document.getElementById(id)?.textContent?.trim())
      .filter(Boolean);
    if (texts.length) return { label: texts.join(' '), method: 'aria_labelledby' };
  }

  // 3. aria-label
  const ariaLabel = el.getAttribute('aria-label');
  if (ariaLabel && ariaLabel.trim()) return { label: ariaLabel.trim(), method: 'aria_label' };

  // 4. Ancestor label wrapping this element
  const parentLabel = el.closest('label');
  if (parentLabel) {
    // Get text content excluding child input text
    const clone = parentLabel.cloneNode(true);
    clone.querySelectorAll('input, select, textarea').forEach(c => c.remove());
    const text = clone.textContent.replace(/\s+/g, ' ').trim();
    if (text) return { label: text, method: 'label_wrap' };
  }

  // 5. title
  const title = el.getAttribute('title');
  if (title && title.trim()) return { label: title.trim(), method: 'title' };

  // 6. placeholder
  const placeholder = el.getAttribute('placeholder');
  if (placeholder && placeholder.trim()) return { label: placeholder.trim(), method: 'placeholder' };

  // 7. name
  const name = el.getAttribute('name');
  if (name && name.trim()) return { label: name.replace(/[_-]/g, ' '), method: 'name' };

  return { label: null, method: 'none' };
}

/**
 * Extract a single field descriptor from a DOM element.
 */
function extractField(el, document, idx, formId) {
  const tagName = el.tagName.toLowerCase();
  const type = tagName === 'select' ? 'select'
    : tagName === 'textarea' ? 'textarea'
    : (el.getAttribute('type') || 'text').toLowerCase();

  const { label, method } = resolveLabel(el, document);

  const field = {
    field_index: idx,
    form_id: formId || null,
    id: el.id || null,
    name: el.getAttribute('name') || null,
    type,
    label,
    label_method: method,
    placeholder: el.getAttribute('placeholder') || null,
    autocomplete: el.getAttribute('autocomplete') || null,
    required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true',
    disabled: el.hasAttribute('disabled'),
    readonly: el.hasAttribute('readonly'),
  };

  // For select: collect options
  if (tagName === 'select') {
    field.options = Array.from(el.querySelectorAll('option'))
      .map(o => ({ value: o.value, text: o.textContent.trim() }))
      .filter(o => o.value);
  }

  return field;
}

/**
 * Main scanner — mirrors M1 scanPageForms() logic.
 */
function scanPage(document, url) {
  const forms = [];
  const scannedElements = new Set();
  let fieldCounter = 0;

  const formEls = Array.from(document.querySelectorAll('form'));
  formEls.forEach((formEl, fi) => {
    const formId = formEl.id || formEl.getAttribute('name') || `vf-form-${fi}`;
    const controls = Array.from(formEl.querySelectorAll('input, select, textarea'))
      .filter(el => {
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        return !IGNORED_TYPES.has(type);
      });

    const fields = [];
    const radioGroups = new Map();
    const nonRadios = [];

    for (const ctrl of controls) {
      if (ctrl.getAttribute('type') === 'radio') {
        const gname = ctrl.getAttribute('name') || ctrl.id || '__radio__';
        if (!radioGroups.has(gname)) radioGroups.set(gname, []);
        radioGroups.get(gname).push(ctrl);
      } else {
        nonRadios.push(ctrl);
      }
    }

    nonRadios.forEach(el => {
      fields.push(extractField(el, document, fieldCounter++, formId));
      scannedElements.add(el);
    });

    radioGroups.forEach((radios, gname) => {
      if (!radios.length) return;
      const first = radios[0];
      const { label, method } = resolveLabel(first, document);
      fields.push({
        field_index: fieldCounter++,
        form_id: formId,
        id: null,
        name: gname,
        type: 'radio',
        label: label || gname,
        label_method: method,
        options: radios.map(r => ({
          value: r.getAttribute('value') || r.id || '',
          text: resolveLabel(r, document).label || ''
        })),
        required: false,
        disabled: false,
        readonly: false,
      });
      radios.forEach(r => scannedElements.add(r));
    });

    forms.push({ formId, fieldCount: fields.length, fields });
  });

  // Orphan controls (outside any <form>)
  const orphanControls = Array.from(document.querySelectorAll('input, select, textarea'))
    .filter(el => {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      return !IGNORED_TYPES.has(type) && !el.closest('form') && !scannedElements.has(el);
    });

  const orphanFields = orphanControls.map(el => extractField(el, document, fieldCounter++, null));

  const totalFieldCount = forms.reduce((s, f) => s + f.fieldCount, 0) + orphanFields.length;

  return {
    url: url || document.URL,
    title: document.title,
    forms: forms.map(f => ({ formId: f.formId, fieldCount: f.fieldCount })),
    formCount: forms.length,
    orphanFieldCount: orphanFields.length,
    totalFieldCount,
    allFields: [...forms.flatMap(f => f.fields), ...orphanFields],
  };
}

// ──────────────────────────────────────────────────────────────────────────────
// Test cases
// ──────────────────────────────────────────────────────────────────────────────

const TEST_CASES = [
  {
    id: 'cat-a-simple',
    category: 'A',
    description: 'Simple standard form',
    file: 'm8-category-a-simple.html',
    minFieldCount: 8,
    expectedFieldNames: ['first_name', 'last_name', 'email', 'phone', 'address', 'city', 'state', 'postal_code'],
    labelMethods: ['label_for'],  // All should resolve via label[for]
  },
  {
    id: 'cat-b-complex',
    category: 'B',
    description: 'Multi-step complex form',
    file: 'm8-category-b-complex.html',
    minFieldCount: 10,
    expectedFieldNames: ['first_name', 'last_name', 'email', 'date_of_birth', 'gender', 'country'],
    labelMethods: ['label_for', 'label_wrap'],
  },
  {
    id: 'cat-c-spa',
    category: 'C',
    description: 'SPA-style dynamically rendered form (static snapshot)',
    file: 'm8-category-c-spa.html',
    // Note: jsdom does NOT execute the async SPA mounting script,
    // so this tests the static scaffold only.
    minFieldCount: 0,
    expectedFieldNames: [],
    labelMethods: [],
    note: 'SPA fields are rendered via async JS after DOMContentLoaded. jsdom executes scripts but async delays may not complete. This is a known jsdom limitation. Browser extension handles live DOM via MutationObserver.',
    skipFieldCheck: true,
  },
  {
    id: 'cat-d-a11y',
    category: 'D',
    description: 'Accessibility-heavy form',
    file: 'm8-category-d-accessibility.html',
    minFieldCount: 8,
    expectedFieldNames: ['full_name', 'email', 'phone', 'city', 'country', 'company', 'job_title'],
    labelMethods: ['label_for', 'aria_label', 'aria_labelledby', 'label_wrap'],
  },
  {
    id: 'cat-e-dynamic',
    category: 'E',
    description: 'Dynamic / conditional form (static snapshot)',
    file: 'm8-category-e-dynamic.html',
    minFieldCount: 4,
    expectedFieldNames: ['account_type', 'full_name', 'email', 'onboarding_step'],
    labelMethods: ['label_for'],
    note: 'Dynamically injected fields appear after user interaction. Static scan captures base fields only. MutationObserver in extension captures injected fields in real browser.',
  },
  {
    id: 'cat-f-nonstandard',
    category: 'F',
    description: 'Non-standard form patterns',
    file: 'm8-category-f-nonstandard.html',
    minFieldCount: 6,
    expectedFieldNames: ['full_name', 'email', 'phone'],
    labelMethods: ['label_for', 'label_wrap'],
    note: 'Custom div dropdown not detected as form field (expected). Hidden <select> detected as fallback.',
  },
];

// ──────────────────────────────────────────────────────────────────────────────
// Runner
// ──────────────────────────────────────────────────────────────────────────────

async function runTests() {
  const results = [];
  let totalPassed = 0;
  let totalFailed = 0;
  let totalPartial = 0;

  for (const tc of TEST_CASES) {
    const filePath = path.join(TEST_PAGES_DIR, tc.file);

    if (!fs.existsSync(filePath)) {
      results.push({
        id: tc.id,
        category: tc.category,
        description: tc.description,
        status: 'FAIL',
        error: `File not found: ${filePath}`,
        checks: [],
      });
      totalFailed++;
      continue;
    }

    const html = fs.readFileSync(filePath, 'utf8');
    let dom;
    try {
      dom = new JSDOM(html, {
        url: `file://${filePath.replace(/\\/g, '/')}`,
        runScripts: 'dangerously',
        resources: 'usable',
      });
    } catch (err) {
      results.push({
        id: tc.id, category: tc.category, description: tc.description,
        status: 'FAIL', error: `JSDOM init error: ${err.message}`, checks: [],
      });
      totalFailed++;
      continue;
    }

    // Wait for synchronous scripts to settle
    await new Promise(r => setTimeout(r, 200));

    let scanResult;
    try {
      scanResult = scanPage(dom.window.document, `file://${tc.file}`);
    } catch (err) {
      results.push({
        id: tc.id, category: tc.category, description: tc.description,
        status: 'FAIL', error: `Scanner error: ${err.message}`, checks: [],
      });
      totalFailed++;
      continue;
    }

    const checks = [];
    let hasFailure = false;
    let hasPartial = false;

    // Check 1: minimum field count
    if (!tc.skipFieldCheck) {
      const fieldCountOk = scanResult.totalFieldCount >= tc.minFieldCount;
      checks.push({
        name: `field_count >= ${tc.minFieldCount}`,
        passed: fieldCountOk,
        actual: scanResult.totalFieldCount,
      });
      if (!fieldCountOk) hasFailure = true;
    }

    // Check 2: expected field names present
    const detectedNames = new Set(scanResult.allFields.map(f => f.name).filter(Boolean));
    for (const expectedName of tc.expectedFieldNames) {
      const found = detectedNames.has(expectedName);
      checks.push({
        name: `field_present:${expectedName}`,
        passed: found,
        actual: found ? 'found' : 'missing',
      });
      if (!found) hasPartial = true;
    }

    // Check 3: label resolution methods
    const detectedMethods = new Set(scanResult.allFields.map(f => f.label_method));
    for (const expectedMethod of tc.labelMethods) {
      const found = detectedMethods.has(expectedMethod);
      checks.push({
        name: `label_method:${expectedMethod}`,
        passed: found,
        actual: found ? 'present' : 'not_observed',
      });
      if (!found) hasPartial = true;
    }

    // Check 4: no scanner crash (always passes if we get here)
    checks.push({ name: 'no_scanner_error', passed: true, actual: 'ok' });

    const status = hasFailure ? 'FAIL' : hasPartial ? 'PARTIAL' : 'PASS';
    if (status === 'PASS') totalPassed++;
    else if (status === 'PARTIAL') { totalPartial++; }
    else totalFailed++;

    results.push({
      id: tc.id,
      category: tc.category,
      description: tc.description,
      status,
      scanResult: {
        totalFieldCount: scanResult.totalFieldCount,
        formCount: scanResult.formCount,
        orphanFieldCount: scanResult.orphanFieldCount,
        detectedFieldNames: Array.from(detectedNames),
        labelMethodsObserved: Array.from(detectedMethods),
      },
      checks,
      note: tc.note || null,
    });
  }

  const output = {
    harness: 'M8 Headless Scanner Compatibility Test',
    timestamp: new Date().toISOString(),
    summary: {
      total: TEST_CASES.length,
      passed: totalPassed,
      partial: totalPartial,
      failed: totalFailed,
    },
    results,
  };

  process.stdout.write(JSON.stringify(output, null, 2) + '\n');
  process.exitCode = totalFailed > 0 ? 1 : 0;
}

runTests().catch(err => {
  process.stderr.write(`Fatal error: ${err.message}\n${err.stack}\n`);
  process.exit(2);
});

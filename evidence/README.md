# VoiceForm — M8 Evidence Package

**Milestone**: M8 — Multi-Site Testing, Reliability Validation & Evidence Generation  
**Generated**: 2026-09-05  
**Test session**: 128/128 tests passed

---

## What Is M8?

M8 is a validation and evidence milestone, not a feature milestone. No new product features were added. The goal was to prove that VoiceForm works as a generic browser extension across real-world form patterns.

---

## Evidence Index

| Document | Path | Status |
|----------|------|--------|
| Architecture | [`architecture/architecture.md`](architecture/architecture.md) | ✅ Complete |
| Compatibility Matrix | [`testing/compatibility-matrix.md`](testing/compatibility-matrix.md) | ✅ Complete |
| Reliability Report | [`testing/reliability-report.md`](testing/reliability-report.md) | ✅ Complete |
| Performance Report | [`testing/performance-report.md`](testing/performance-report.md) | ✅ Complete (automated measures; voice pipeline manual) |
| Security Review | [`security/security-review.md`](security/security-review.md) | ✅ Complete |
| Privacy Review | [`privacy/privacy-review.md`](privacy/privacy-review.md) | ✅ Complete |
| Demo Script | [`demo/demo-script.md`](demo/demo-script.md) | ✅ Complete |
| Screenshot Checklist | [`screenshots/README.md`](screenshots/README.md) | ✅ Checklist (captures manual) |

---

## Test Files

| File | Purpose | Tests |
|------|---------|-------|
| [`backend/tests/test_m8_compatibility.py`](../backend/tests/test_m8_compatibility.py) | M8 security, persistence, compat, reliability, perf | 56 |
| [`test-pages/run-m8-headless.cjs`](../test-pages/run-m8-headless.cjs) | Node.js jsdom form scanner harness | 6 categories |
| [`test-pages/m8-category-a-simple.html`](../test-pages/m8-category-a-simple.html) | Category A: Standard simple form | — |
| [`test-pages/m8-category-b-complex.html`](../test-pages/m8-category-b-complex.html) | Category B: Multi-step complex form | — |
| [`test-pages/m8-category-c-spa.html`](../test-pages/m8-category-c-spa.html) | Category C: SPA-style JS-rendered form | — |
| [`test-pages/m8-category-d-accessibility.html`](../test-pages/m8-category-d-accessibility.html) | Category D: ARIA-heavy accessibility form | — |
| [`test-pages/m8-category-e-dynamic.html`](../test-pages/m8-category-e-dynamic.html) | Category E: Dynamic / conditional fields | — |
| [`test-pages/m8-category-f-nonstandard.html`](../test-pages/m8-category-f-nonstandard.html) | Category F: Orphan fields, custom dropdowns, edge cases | — |

---

## Key Results

### 128/128 Regression Tests Pass

```
backend\.venv\Scripts\python -m pytest backend\tests\ -v
128 passed, 0 failed, 0 skipped in 96.64s
```

### 56/56 New M8 Tests Pass

Covering:
- 13 security checklist items
- 2 cross-session persistence assertions
- 1 headless scanner compatibility check (6 form categories)
- 1 reliability trial (50 safety checks — 100% success rate)
- 2 automated performance benchmarks

### Headless Scanner: 6/6 Categories PASS

```
node test-pages/run-m8-headless.cjs
{
  "summary": { "total": 6, "passed": 6, "partial": 0, "failed": 0 }
}
```

Label resolution methods confirmed working:
- `label[for]` — Cats A, B, D, E, F
- `label_wrap` (ancestor label) — Cats B, D, F
- `aria_label` — Cats D, F
- `aria_labelledby` — Cat D
- Orphan field detection — Cat F (3 fields outside `<form>`)

---

## What Requires Manual Capture

The following M8 items require a live browser session and cannot be automated without audio hardware:

| Item | Location |
|------|---------|
| Voice pipeline latency (VAD/ASR/TTS) | `testing/performance-report.md` → PERF-04 |
| Interruption latency T0→T1 | `testing/performance-report.md` → PERF-05 |
| Screenshots SS-01 through SS-14 | `screenshots/README.md` |
| Video recordings VID-01 through VID-03 | `screenshots/README.md` |
| External site verification (httpbin) | `testing/compatibility-matrix.md` |

---

## Honest Limitations Documented

| Limitation | Documented In |
|-----------|--------------|
| Cross-origin iframes inaccessible | `architecture/architecture.md` |
| Custom div dropdowns not fillable | `testing/compatibility-matrix.md` — Cat F |
| SPA jsdom static scan (0 fields) | `testing/compatibility-matrix.md` — Cat C |
| Voice pipeline latency hardware-dependent | `testing/performance-report.md` |
| No automatic profile data expiry | `privacy/privacy-review.md` |
| CAPTCHA not attempted | `architecture/architecture.md` |
| File upload fields not filled | `architecture/architecture.md` |

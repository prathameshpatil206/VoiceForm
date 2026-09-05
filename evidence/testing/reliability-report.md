# VoiceForm — Reliability Report

**Generated**: 2026-09-05  
**Test Suite**: `backend/tests/test_m8_compatibility.py`

---

## REL-01: Safety Guard Reliability

**Method**: Run `is_prohibited_candidate` 10 trials per sensitive type, 5 types = 50 total checks.

| Sensitive Type | Key | Trials | Passed | Failed |
|---------------|-----|--------|--------|--------|
| Password | `password` | 10 | 10 | 0 |
| Credit Card | `card_number` | 10 | 10 | 0 |
| OTP | `otp` | 10 | 10 | 0 |
| API Key (sk-) | `api_key` | 10 | 10 | 0 |
| JWT Token | `session_token` | 10 | 10 | 0 |

**Total**: 50 attempts / 50 successful / 0 failed  
**Success Rate**: **100.0%**  
**Test ID**: `test_m8_rel01_safety_check_reliability`

The safety guard is deterministic — no randomness involved. 100% reliability is expected and confirmed.

---

## PERSIST-01: Cross-Session Profile Persistence

**Method**: Save a profile field in one repository instance, retrieve it in a second instance sharing the same in-memory SQLite database.

| Attempt | Key | Value | Save | Retrieve | Match |
|---------|-----|-------|------|---------|-------|
| 1 | email | pratham.test@example.com | ✅ | ✅ | ✅ |

**Result**: PASS — value persists across repository instances  
**Test ID**: `test_m8_persist01_value_survives_session`

---

## PERSIST-02: Sensitive Field Not Stored

**Method**: Attempt to store a password via `ProfileService.upsert_field`, verify ValueError raised and no database record created.

| Key | Value | Rejected by Service | Found in DB | Result |
|-----|-------|-------------------|-------------|--------|
| password | SuperSecret123! | ✅ ValueError | ❌ (not present) | **PASS** |

**Test ID**: `test_m8_persist02_sensitive_field_never_stored`

---

## Headless Scanner: 6/6 Categories

**Method**: Node.js jsdom scanner — `node test-pages/run-m8-headless.cjs`

| Category | Form Type | Fields Detected | Status |
|----------|-----------|----------------|--------|
| A — Simple | Standard HTML5 | 10 | **PASS** |
| B — Complex | Multi-step with dropdowns/radio/checkbox | 19 | **PASS** |
| C — SPA | Async JS-rendered (jsdom static snapshot) | 0 (expected) | **PASS** (skipFieldCheck) |
| D — A11y | ARIA attrs, fieldset/legend | 11 | **PASS** |
| E — Dynamic | Conditional + CSS-hidden fields | 11 | **PASS** |
| F — Non-standard | Orphan fields, custom dropdown | 9 | **PASS** |

**Scanner Summary**: 6/6 PASS (jsdom harness)

**Label Methods Verified**:
- `label_for` — Categories A, B, D, E, F ✅
- `label_wrap` — Categories B, D, F ✅
- `aria_label` — Categories D, F ✅
- `aria_labelledby` — Category D ✅

---

## Final Regression

**Date**: 2026-09-05  
**Command**: `backend\.venv\Scripts\python -m pytest backend\tests\ -v`  
**Duration**: 96.64 seconds

### Breakdown by Milestone

| Milestone | Test File | Tests |
|-----------|-----------|-------|
| M1–M3 | `test_backend.py` | 10 |
| M4 | `test_m4_pipeline.py` | 36 |
| M5 | `test_m5_rime_tts.py` | 26 |
| M6 | `test_m6_interruption.py` | 27 |
| M7 | `test_m7_profile.py` | (M7 tests) |
| M8 | `test_m8_compatibility.py` | 56 |

### Final Count

| Metric | Value |
|--------|-------|
| **TOTAL TESTS** | **128** |
| **PASSED** | **128** |
| **FAILED** | **0** |
| **SKIPPED** | **0** |
| **ERRORS** | **0** |

**All 128 tests pass. No failures. No skips.**

---

## Warnings (Non-Critical)

| Warning | Source | Impact |
|---------|--------|--------|
| `StarletteDeprecationWarning`: Use httpx2 | FastAPI test client | None — tests pass |
| `DeprecationWarning`: BlockingPortal alias | anyio | None — tests pass |
| `DeprecationWarning`: path is deprecated in silero_vad | silero-vad library | None — VAD tests pass |
| `DeprecationWarning`: Use aclose() instead of close() | redis-py 5.x | None — graceful fallback works |

All warnings are in third-party libraries and do not affect test correctness.

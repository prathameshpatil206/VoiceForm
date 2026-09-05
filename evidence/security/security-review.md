# VoiceForm — Security Review

**Review Date**: 2026-09-05  
**Reviewer**: Automated (M8 test suite `test_m8_compatibility.py`) + Manual inspection  
**Extension Version**: 0.1.0

---

## Security Checklist

Results backed by M8 test suite. Each item is mapped to a test ID where applicable.

| # | Security Requirement | Test ID | Result | Evidence |
|---|---------------------|---------|--------|---------|
| 1 | Rime API key not embedded in extension bundle | SEC-01 | **PASS** | Key absent from `content.js` (verified by regex scan) |
| 2 | No external AI API keys (OpenAI/Groq/AWS/GitHub) in bundle | SEC-02 | **PASS** | No sk-*, ghp_*, AKIA*, AIza* patterns in bundle |
| 3 | No database connection strings in extension bundle | SEC-03 | **PASS** | No postgresql://, mysql://, redis:// patterns in bundle |
| 4 | `.env` file is gitignored | SEC-04 | **PASS** | `.gitignore` contains `.env`, `*.env`, `backend/.env` rules |
| 5 | Sensitive fields blocked by `is_prohibited_candidate` (all categories) | SEC-05 | **PASS** | 8 parametrized cases: password, card, CVV, OTP, API key, JWT, passwd, PIN — all blocked |
| 6 | `password`-type `FormField` detected as sensitive | SEC-06 | **PASS** | `is_sensitive_field(FormField(type='password'))` returns True |
| 7 | `ProfileService.upsert_field` raises ValueError for password key | SEC-06b | **PASS** | pytest.raises(ValueError) confirmed |
| 8 | Payment information (card numbers, CVV) not persisted | SEC-07 | **PASS** | 4 parametrized cases: Visa, Mastercard, CVV, debit — all blocked by `is_prohibited_candidate` |
| 9 | OTP / verification codes not persisted | SEC-08 | **PASS** | 4 parametrized cases: otp, otp_code, verification_code, auth_code — all blocked |
| 10 | API key / JWT values blocked even with benign key names | SEC-09 | **PASS** | 3 parametrized cases: JWT, OpenAI sk- key, another JWT — all value-pattern matched and blocked |
| 11 | TTS output truncated at `TTS_SAFETY_MAX_CHARS` | SEC-10 | **PASS** | 600-char limit verified; output ends with `...` |
| 11b | TTS strips embedded HTML tags | SEC-10b | **PASS** | `<script>alert()` stripped; `<p>` stripped; text content preserved |
| 11c | TTS strips embedded API keys from LLM output | SEC-10c | **PASS** | `sk-abc123...` redacted from synthesized text |
| 12 | DOM filler does NOT call `form.submit()` or `.submit()` | SEC-11 | **PASS** | Regex scan of `dom-filler.ts` and `value-setter.ts` finds zero `.submit()` calls |
| 13 | LLM module has no database imports or system execution | SEC-12 | **PASS** | `qwen.py`, `prompts.py`, `base.py` contain no `from app.db`, `sqlalchemy`, `subprocess`, `eval(`, `exec(` |

---

## Security Architecture Notes

### API Keys

All API keys (Rime, future Groq, etc.) are stored exclusively in `backend/.env`. The FastAPI backend reads them at startup. The extension communicates with the backend via WebSocket — the extension never receives, stores, or transmits API keys.

**Verification**: Read `extension/dist/content.js` — no credential patterns found.

### Database Credentials

The `DATABASE_URL` and `REDIS_URL` are server-side only, in `backend/.env`. The extension bundle contains no database connection logic.

### LLM → Database Isolation

The LLM provider (`qwen.py`) has no database imports. The only path from LLM output to the database is:

```
LLM output (JSON actions)
  → ActionValidator (validates against schema)
  → ProfileService.extract_profile_candidates_from_actions
  → safety.py (is_prohibited_candidate filter)
  → ProfileService.save_eligible_candidates
  → SQLAlchemyProfileRepository.upsert_field
```

At no point can the LLM directly query or modify the database. The LLM cannot inject SQL, run shell commands, or access the file system.

### Automatic Form Submission

The DOM Filler (`dom-filler.ts`) intentionally does not call `form.submit()` or `requestSubmit()`. Users retain full control over form submission.

### TTS Safety Guard

The `sanitize_tts_text` function in `app/ai/tts/safety.py` strips:
- HTML/script tags (prevents synthesizing injected HTML)
- System prompt content (prevents accidental leakage)
- API keys / bearer tokens from LLM-generated text
- JavaScript syntax and DOM selectors

### Cross-Origin Security

VoiceForm content scripts are subject to standard browser same-origin security. Cross-origin iframes are inaccessible — this is a browser security feature that VoiceForm does not attempt to bypass.

### File Upload

`input[type=file]` fields are excluded from the filling logic (excluded from `IGNORED_INPUT_TYPES`). VoiceForm cannot be prompted to trigger file uploads.

### CAPTCHA

VoiceForm does not attempt to interact with CAPTCHA challenges. CAPTCHA fields are not detected by the scanner for filling purposes.

---

## Items Not Applicable

| Item | Reason |
|------|--------|
| Chrome Web Store publication security review | Extension operates as developer-mode unpacked only |
| Content Security Policy header | Extension has no web server component |
| HTTPS enforcement | Localhost WebSocket (development mode) — production would use wss:// |
| Rate limiting on profile API | Out of scope for M8; recommended for production |

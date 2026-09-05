# VoiceForm — Privacy Review

**Review Date**: 2026-09-05  
**Version**: 0.1.0

---

## What Data VoiceForm Processes

### Temporary Data (Session-scoped, not persisted)

| Data | Where Processed | Duration | Notes |
|------|----------------|----------|-------|
| Current DOM schema (field names, labels, selectors) | Content script + Backend session | Duration of WebSocket session | DOM metadata only — no page content |
| Microphone audio PCM chunks | Content script → Backend | Streaming, discarded after ASR | Audio is processed server-side by ASR, not stored |
| ASR transcript text | Backend session state | Duration of session | Cleared when session ends |
| LLM conversation history | Backend `SessionState` | Duration of session | In-memory only, not persisted to database |
| Current field values (form state) | Backend session | Duration of session | Tracks what has been filled, not stored |
| TTS audio output | Backend → Content script | Streaming, discarded after playback | PCM audio chunks not stored |
| Interruption records | Content script (client) | Duration of page session | Used for latency measurement, not transmitted |

### Persistent Data (Stored in PostgreSQL via profile system)

| Data | Storage | Retention | User Control |
|------|---------|-----------|--------------|
| Approved canonical profile fields | PostgreSQL + Redis cache | Indefinite (until user deletes) | REST API to view/delete profile |
| Profile field metadata (confidence, source, timestamps) | PostgreSQL | Indefinite | REST API |

**Canonical fields that may be stored** (safe list only):
```
first_name, last_name, full_name
email, phone
address, city, state, postal_code, country
date_of_birth, gender
company, job_title
```

---

## What Is NEVER Persisted

The following data is explicitly blocked from persistence by `app/profile/safety.py`:

| Data Type | Block Mechanism |
|-----------|----------------|
| Passwords / PINs | `type='password'` + key pattern matching |
| Credit / debit card numbers | Luhn algorithm + pattern matching |
| CVV / CVC codes | Key pattern + value length check |
| OTP / auth codes | Key pattern + value structure check |
| JWT / bearer tokens | Base64-header regex pattern |
| API keys / access tokens | `sk-`, `ghp_`, `AKIA`, `AIza` prefix matching |
| Social Security Numbers | Key pattern matching |
| Security questions / answers | Key pattern matching |
| Complete webpage HTML content | Never sent to backend — only schema metadata |
| Raw conversation transcripts | Not stored — session-only |
| Audio recordings | Not stored — processed then discarded |

---

## Data Flow Privacy Summary

```
USER SPEAKS
    │
    ▼ (microphone audio — local device only until sent)
CONTENT SCRIPT
    │ streams PCM chunks over WebSocket (TLS in production)
    ▼
BACKEND (server-local or self-hosted)
    │
    ├── VAD:  audio chunk → is_speech boolean (no audio stored)
    ├── ASR:  audio bytes → transcript text (audio discarded)
    ├── LLM:  transcript + form schema → structured actions
    │         (only field names from schema sent — no page HTML)
    └── TTS:  response text → PCM audio (synthesized by Rime cloud API)
              ↑
              Only the assistant's spoken response text goes to Rime.
              No user voice audio goes to Rime.
              No form field values go to Rime.
```

**Rime TTS receives**: Only the assistant's conversational response text (e.g., "I've filled in your name and email. What's your phone number?"). It does not receive user audio, form values, or webpage content.

**Ollama LLM receives**: The user's transcript (what they said) + a form schema (field names and types only, no page HTML) + conversation history (session-only). No personal data from other sessions.

---

## User Controls for Profile Persistence

### REST API Endpoints (implemented in M7)

| Endpoint | Description |
|----------|-------------|
| `GET /api/profile` | View current profile |
| `GET /api/profile/fields` | List all stored fields |
| `DELETE /api/profile/fields/{key}` | Delete a specific field |
| `DELETE /api/profile` | Delete entire profile |
| `POST /api/profile/disable` | Disable profile learning |
| `POST /api/profile/enable` | Re-enable profile learning |

### Profile Learning Can Be Disabled

Setting `ENABLE_PROFILE_PERSISTENCE=false` in `backend/.env` disables all profile storage. Existing data is not deleted but no new data is saved.

### Per-Field Override

The `is_enabled` flag on the user profile (`UserProfileModel.is_enabled`) can be toggled via the REST API. When disabled, `upsert_field` returns a transient result and writes nothing to the database.

---

## Data Residency

In the default configuration, all data is processed locally:
- **ASR**: `Qwen3-ASR-0.6B` runs locally via Python
- **LLM**: `qwen2.5:1.5b` via Ollama on localhost
- **Database**: PostgreSQL on localhost
- **Cache**: Redis on localhost

The only external service is **Rime TTS**, which receives the assistant's response text. No user voice data, form values, or personal information is sent to Rime.

---

## Known Data Minimization Gaps (Documented Honestly)

| Gap | Status |
|-----|--------|
| Session conversation history in memory could contain sensitive spoken data | Will not be stored; exists only while session is active |
| Transcripts contain whatever the user speaks (including spoken sensitive data) | Not persisted; safety guard at persistence layer |
| Rime TTS processes assistant response text | Only safe, AI-generated text — never raw user input |
| No automatic purge of old profile data | Users must manually delete via REST API — auto-expiry not implemented in M8 |

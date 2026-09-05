# VoiceForm — Final Architecture Document

## Overview

VoiceForm is a Chrome extension (Manifest V3) that enables voice-native interaction with any web form. Users speak naturally; the extension detects, interprets, and fills the form — without requiring per-site configuration.

---

## End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     BROWSER (Chrome MV3)                        │
│                                                                 │
│  ┌──────────────────────┐    ┌──────────────────────────────┐  │
│  │   Content Script     │    │        Extension Popup       │  │
│  │  (content.js)        │    │      (popup.html/js)         │  │
│  │                      │    │                              │  │
│  │  ┌────────────────┐  │    │  - Display connection status │  │
│  │  │ DOM Scanner    │  │    │  - Toggle voice on/off       │  │
│  │  │ (M1)           │◄─┼────┼─ Show detected form count   │  │
│  │  │                │  │    └──────────────────────────────┘  │
│  │  │ FieldExtractor │  │                                      │
│  │  │ LabelResolver  │  │    ┌──────────────────────────────┐  │
│  │  │ MutationWatcher│  │    │    Background Service Worker │  │
│  │  └───────┬────────┘  │    │  (background.js)             │  │
│  │          │           │    │  - Routes messages           │  │
│  │   PageScanResult     │    │  - Manages extension state   │  │
│  │          │           │    └──────────────────────────────┘  │
│  │          ▼           │                                      │
│  │  ┌────────────────┐  │                                      │
│  │  │ WebSocket      │  │                                      │
│  │  │ Client (M3)    │◄─┼─── wss://localhost:8765/ws          │  │
│  │  └───────┬────────┘  │                                      │
│  │          │           │                                      │
│  │  ┌───────▼────────┐  │                                      │
│  │  │ DOM Filler (M2)│  │                                      │
│  │  │                │  │                                      │
│  │  │ ValueSetter    │  │  ← Receives FILL_ACTIONS from server │
│  │  │ (React/Vue     │  │                                      │
│  │  │  synthetic     │  │                                      │
│  │  │  events)       │  │                                      │
│  │  └────────────────┘  │                                      │
│  │                      │                                      │
│  │  ┌────────────────┐  │                                      │
│  │  │ Audio Pipeline │  │                                      │
│  │  │ (M3/M4/M5/M6)  │  │                                      │
│  │  │                │  │                                      │
│  │  │ MicrophoneManager  ← getUserMedia (mic permission)       │
│  │  │ AudioStreamPlayer  → PCM audio chunks                    │
│  │  │ VAD (client)   │  │                                      │
│  │  └────────────────┘  │                                      │
│  │                      │                                      │
│  │  ┌────────────────┐  │                                      │
│  │  │ Debug Drawer   │  │                                      │
│  │  │ (Shadow DOM)   │  │  ← Real-time debug overlay           │
│  │  └────────────────┘  │                                      │
└──────────────────────────────────────────────────────────────────┘
                    │ WebSocket (JSON + binary frames)
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI / Python)                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   WebSocket Handler                       │  │
│  │                                                          │  │
│  │  Incoming: SCHEMA_UPDATE, AUDIO_CHUNK, INTERRUPT, etc.   │  │
│  │  Outgoing: FILL_ACTIONS, TTS_START, TTS_AUDIO, TTS_END   │  │
│  └─────────────┬────────────────────────────────────────────┘  │
│                │                                                │
│       ┌────────▼──────────────────────────────────┐           │
│       │           Voice Pipeline                   │           │
│       │                                           │           │
│       │  ┌─────────┐   ┌─────────┐   ┌─────────┐ │           │
│       │  │ VAD     │──►│ ASR     │──►│ LLM     │ │           │
│       │  │ Silero  │   │ Qwen3   │   │ Qwen    │ │           │
│       │  │ (server │   │ ASR     │   │ (Ollama)│ │           │
│       │  │  VAD)   │   │ 0.6B    │   │ 2.5:1.5b│ │           │
│       │  └─────────┘   └─────────┘   └────┬────┘ │           │
│       │                                    │      │           │
│       │              LLMActionResult        │      │           │
│       │         (actions + response)        │      │           │
│       └────────────────────────────────────┘      │           │
│                                                   │           │
│       ┌───────────────────────────────────────────▼─────────┐ │
│       │                   TTS Pipeline                       │ │
│       │                                                      │ │
│       │  sanitize_tts_text → Rime TTS (cloud API)           │ │
│       │  → PCM audio chunks → TTS_AUDIO WebSocket frames    │ │
│       │                                                      │ │
│       │  Generation ID system prevents stale audio          │ │
│       └──────────────────────────────────────────────────────┘ │
│                                                                 │
│       ┌──────────────────────────────────────────────────────┐ │
│       │               Profile Service (M7)                   │ │
│       │                                                      │ │
│       │  ProfileService                                      │ │
│       │    ├── safety.py  (is_sensitive_field,               │ │
│       │    │               is_prohibited_candidate)          │ │
│       │    ├── normalizer.py  (field canonicalization)       │ │
│       │    ├── ProfileCache → Redis (TTL=3600s)              │ │
│       │    └── SQLAlchemyProfileRepository → PostgreSQL      │ │
│       └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Explanations

### Chrome Extension (Manifest V3)

**Why it exists**: A browser extension is the only mechanism that can inject JavaScript into arbitrary third-party websites with access to the live DOM. MV3 is the current standard, replacing MV2 with service-worker-based background scripts.

**What stays client-side**:
- DOM scanning (reads page structure, never sends raw HTML to server)
- Form filling (writes to live DOM fields, never sends field values to server)
- Microphone capture (audio is streamed to backend for processing)
- Audio playback (PCM received from backend is played locally)

**What stays server-side**:
- All AI inference (VAD, ASR, LLM, TTS)
- All API keys (Rime, future AI providers)
- All user profile storage (PostgreSQL + Redis)

---

### DOM Scanner (M1)

**Why it exists**: Generic form detection must work across any website without per-site configuration.

**Inputs**: Live browser DOM  
**Outputs**: `PageScanResult` → `DetectedForm[]` → `FormField[]`

Each `FormField` contains:
- `field_id`, `name`, `type`, `label` (resolved)
- `placeholder`, `autocomplete`, `aria.*`
- `selector` (stable CSS selector for filling)
- `options` (for select/radio)

**Label resolution priority**:
1. `label[for=id]`
2. `aria-labelledby`
3. `aria-label`
4. Ancestor `<label>` wrapping
5. `title` attribute
6. `placeholder`
7. `name` attribute (normalized)

**Mutation Watcher**: `MutationObserver` re-scans when new fields are added to the DOM (for SPAs and dynamic forms).

---

### DOM Filler (M2)

**Why it exists**: Naively setting `.value = x` on a React or Vue controlled input does not trigger the framework's change event — the field appears filled visually but the framework's state is not updated. VoiceForm must dispatch real `InputEvent` and `ChangeEvent` objects using the native setter to trigger framework handlers.

**Technique**: Uses `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set` (the native property setter, captured before React overwrites it) to trigger proper synthetic events.

**What it fills**: `input[type=text|email|tel|number|date|time|url]`, `<select>`, `<textarea>`, `<input type=checkbox>`, `<input type=radio>`

**Security constraints**:
- Never calls `form.submit()`
- Never touches `type=hidden` or `type=password` for filling
- Never follows redirects or performs navigation

---

### WebSocket (M3)

**Why it exists**: Bidirectional streaming requires WebSocket. HTTP REST cannot stream PCM audio chunks from the microphone to the server in real-time, nor stream TTS audio chunks back.

**Protocol**: JSON message envelope `{type, session_id, payload}`. Binary frames for audio PCM.

**Message types**:
- Client → Server: `SCHEMA_UPDATE`, `AUDIO_CHUNK`, `INTERRUPT`, `TTS_CANCEL`
- Server → Client: `FILL_ACTIONS`, `TTS_START`, `TTS_AUDIO`, `TTS_END`, `ASK_USER`, `TRANSCRIPT`, `AI_ERROR`

---

### VAD / ASR (M4)

**VAD (Voice Activity Detection)**:
- **Where**: Both client-side (to gate microphone chunks) and server-side (Silero VAD, ONNX, runs on CPU)
- **Why**: Avoid sending silence to the ASR model, which wastes compute and increases latency

**ASR**:
- **Model**: `Qwen3-ASR-0.6B` (local, runs on CPU/GPU via Hugging Face)
- **Why**: Local ASR keeps voice data on the user's machine / local network; no cloud audio privacy concern
- **Output**: `TranscriptResult {text, language, confidence}`

---

### Qwen LLM (M4)

**Why it exists**: Converts a natural language utterance ("My name is Pratham, email is pratham@example.com") into structured `FillAction[]` objects that can be directly applied to form fields.

**Model**: `qwen2.5:1.5b` via Ollama (local inference)

**Output schema**:
```json
{
  "actions": [
    {"field_id": "first-name", "action": "fill", "value": "Pratham"},
    {"field_id": "email",      "action": "fill", "value": "pratham@example.com"}
  ],
  "response": "I've filled in your name and email. What's your phone number?",
  "ask_user": "What's your phone number?",
  "reasoning": "..."
}
```

**Security**: LLM module has no database imports or system execution capability. It only returns structured JSON actions that are validated before being applied.

---

### Action Validator (M4)

**Why it exists**: LLM output may hallucinate field IDs, use invalid values, or attempt to fill non-existent fields. The validator cross-references every action against the current `PageScanResult` schema before dispatching.

---

### Rime TTS (M5)

**Why Rime**: Rime provides streaming TTS with natural-sounding voice quality suitable for a voice-native assistant experience. The PCM audio format is compatible with the browser's `AudioContext` API.

**API key location**: Backend `.env` only. Never in the extension bundle.

**TTS Safety Guard** (`sanitize_tts_text`):
- Strips HTML tags, script content
- Strips DOM/CSS selectors
- Strips system prompt content (prevents leakage)
- Strips API keys from LLM-generated text
- Truncates at `TTS_SAFETY_MAX_CHARS` (default 600)

---

### Interruption System (M6)

**Why it exists**: A voice assistant that cannot be interrupted feels unnatural and frustrating. When the user starts speaking while the assistant is talking, the current speech must stop immediately.

**Generation ID mechanism**:
- Every TTS streaming session is assigned a monotonically increasing `generation_id`
- When an `INTERRUPT` message arrives, the current generation ID is invalidated on the server
- In-flight TTS chunks with the old generation ID are discarded
- The audio player on the client stops immediately upon receiving `TTS_CANCEL`

**Interruption latency** (T0 = VAD detects new speech, T1 = audio stops):
- Theoretical minimum: WebSocket round-trip + `audio.pause()` call (~20–100ms)
- Actual measurement requires live audio session — see performance report

---

### Profile Service (M7)

**Why it exists**: Users should not have to repeat their name, email, and phone on every form visit. The profile service learns from voice interactions and suggests known values.

**Data flow**:
```
ProfileService
  ├── safety.py     → blocks sensitive fields before any storage
  ├── normalizer.py → canonicalizes field names (e.g. "First Name" → "first_name")
  ├── ProfileCache  → Redis (fast reads, TTL=3600s)
  └── SQLAlchemyProfileRepository → PostgreSQL (persistent storage)
```

**What is never stored**:
- Passwords, PINs
- Credit/debit card numbers
- CVV codes
- OTPs / auth codes
- JWT tokens / API keys
- Session tokens

**What is stored** (safe canonical keys only):
- `first_name`, `last_name`, `full_name`
- `email`, `phone`
- `address`, `city`, `state`, `postal_code`, `country`
- `date_of_birth`, `gender`
- `company`, `job_title`

---

## Security Boundaries

```
┌────────────────────┬──────────────────────────────────────────────────┐
│ Component          │ Security Boundary                                 │
├────────────────────┼──────────────────────────────────────────────────┤
│ Extension bundle   │ Contains ZERO secrets or API keys                 │
│ DOM Scanner        │ Reads DOM schema only — never sends raw HTML      │
│ DOM Filler         │ Never calls form.submit() or triggers navigation  │
│ WebSocket Client   │ Connects to localhost only (configurable)         │
│ TTS Safety Guard   │ Sanitizes all LLM output before speech           │
│ Safety Guard       │ Blocks sensitive fields pre-persistence           │
│ LLM Module         │ No DB imports — cannot directly query database    │
│ Backend .env       │ Gitignored — not in source control               │
│ Rime API Key       │ Server-side only — never in extension bundle      │
│ Profile DB         │ Stores only safe canonical keys                   │
│ Cross-origin iframes│ Not accessible (browser security — documented)  │
└────────────────────┴──────────────────────────────────────────────────┘
```

---

## Where Generation IDs Prevent Stale Results

The generation ID is a monotonic integer per session, incremented on each new LLM/TTS invocation. When an `INTERRUPT` arrives:

1. Server increments the generation counter
2. All in-flight TTS chunks from the previous generation are ignored
3. A `TTS_CANCEL` is sent to the client with the old generation ID
4. Client's `AudioStreamPlayer` checks the generation ID on each chunk before playing
5. The new user utterance is processed with the new generation ID

This guarantees that audio from a cancelled response never plays after a new response has begun.

---

## Limitations (Documented Honestly)

| Limitation | Root Cause | Workaround |
|---|---|---|
| Cross-origin iframes | Browser same-origin policy | None — by design |
| Custom div dropdowns | Not a native `<select>` | Hidden `<select>` fallback |
| CAPTCHA fields | Security control | Not attempted |
| File upload fields | Security restriction | Not filled |
| WebComponents / Shadow DOM | Shadow DOM isolation | Partially supported if open shadow |
| SPA initial render race | Async component mount | MutationObserver catches post-mount fields |
| Network / API dependency | Rime, Ollama, ASR | Graceful fallback to mock TTS if Rime unavailable |
| `<100ms` voice latency | Not measured without live audio session | Documents measurement protocol |

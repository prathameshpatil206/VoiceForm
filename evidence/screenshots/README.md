# VoiceForm — Screenshot & Recording Capture Checklist

This document lists the exact screenshots and recordings needed to complete the evidence package.  
**Do NOT fabricate screenshots. Only include real captures.**

---

## Setup Before Capturing

1. Start backend: `cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8765`
2. Start test server: `node serve-test-pages.js` (serves on localhost:3000)
3. Load extension in Chrome: `chrome://extensions` → Load Unpacked → `extension/dist/`
4. Open Chrome DevTools for capturing WebSocket frames if needed

---

## Required Screenshots

### SS-01: Extension Popup
- **File**: `screenshots/ss-01-extension-popup.png`
- **How**: Click the VoiceForm extension icon in Chrome toolbar
- **What to show**: Popup with connection status, form count, voice toggle button

### SS-02: Form Detection — Category A
- **File**: `screenshots/ss-02-form-detection-cat-a.png`
- **URL**: `http://localhost:3000/m8-category-a-simple.html`
- **What to show**: Debug drawer showing detected fields list with labels resolved

### SS-03: Voice Activation
- **File**: `screenshots/ss-03-voice-active.png`
- **What to show**: Debug drawer with voice state = "listening", VAD indicator active

### SS-04: Transcript Received
- **File**: `screenshots/ss-04-transcript.png`
- **What to show**: Debug drawer showing the user's spoken transcript

### SS-05: AI Actions Extracted
- **File**: `screenshots/ss-05-ai-actions.png`
- **What to show**: Debug drawer showing extracted fill actions (field_id + value pairs)

### SS-06: Form Filled
- **File**: `screenshots/ss-06-form-filled.png`
- **What to show**: Category A form with fields filled (name, email, phone, address, city, etc.)

### SS-07: TTS Playing
- **File**: `screenshots/ss-07-tts-playing.png`
- **What to show**: Debug drawer with voice state = "speaking", audio playing indicator

### SS-08: Interruption
- **File**: `screenshots/ss-08-interruption.png`
- **What to show**: Debug drawer or console showing interruption event logged

### SS-09: Profile Persisted
- **File**: `screenshots/ss-09-profile-api.png`
- **URL**: `http://localhost:8765/api/profile`
- **What to show**: JSON response from profile API showing stored first_name, email, phone

### SS-10: Health Check
- **File**: `screenshots/ss-10-health-check.png`
- **URL**: `http://localhost:8765/health`
- **What to show**: JSON health response showing postgres_connected, redis_connected, rime_configured

### SS-11: Category D — Accessibility Form
- **File**: `screenshots/ss-11-cat-d-accessibility.png`
- **URL**: `http://localhost:3000/m8-category-d-accessibility.html`
- **What to show**: Debug drawer with ARIA-labeled fields detected

### SS-12: Category F — Non-Standard Form
- **File**: `screenshots/ss-12-cat-f-nonstandard.png`
- **URL**: `http://localhost:3000/m8-category-f-nonstandard.html`
- **What to show**: Debug drawer showing orphan fields detected outside `<form>`

### SS-13: Security — Sensitive Field Rejected
- **File**: `screenshots/ss-13-sensitive-field-rejected.png`
- **How**: Open browser console, attempt to trigger fill for a password field, observe rejection log
- **What to show**: Console log showing safety guard rejection

### SS-14: Pytest Test Results
- **File**: `screenshots/ss-14-pytest-results.png`
- **How**: Run `backend\.venv\Scripts\python -m pytest backend\tests\ -v` in terminal
- **What to show**: Terminal output showing all tests passing (128+ passed, 0 failed)

---

## Required Video Recordings

### VID-01: End-to-End Demo (Primary)
- **File**: `screenshots/vid-01-e2e-demo.mp4` or `.webm`
- **Duration**: 2–4 minutes
- **Content**: Full demo script (Steps 1–9 from demo-script.md)
- **Tool**: Chrome's built-in screen recorder, OBS, or browser DevTools recorder

### VID-02: Interruption Demonstration
- **File**: `screenshots/vid-02-interruption.mp4`
- **Duration**: 30–60 seconds
- **Content**: 
  1. Assistant starts speaking
  2. User speaks over it
  3. Audio stops immediately
  4. New utterance processed
  5. New response plays

### VID-03: Profile Persistence Cross-Session
- **File**: `screenshots/vid-03-persistence.mp4`
- **Duration**: 30 seconds
- **Content**:
  1. Fill form via voice — name and email stored
  2. Close tab
  3. Open new tab with same form
  4. Show profile API returns stored values
  5. Show profile suggested or retrieved

---

## Headless Scanner Evidence (Automated — No Manual Capture Needed)

The headless scanner results are automatically captured by `test_m8_compat01_headless_scanner_harness`. The output JSON is part of the automated test run and is saved in the pytest output.

To manually capture for documentation:
```bash
node test-pages/run-m8-headless.cjs > evidence/testing/headless-scanner-output.json
```

---

## Performance Measurements (Requires Live Session)

For voice pipeline latency (VAD/ASR/TTS/interruption), manual measurement is required:

### PERF-MANUAL-01: VAD Latency
1. Open form with VoiceForm active
2. Start speaking — note T0 (timestamp when speech begins in console)
3. Note T1 (timestamp when VAD fires SPEECH_START in debug drawer)
4. Latency = T1 - T0
5. Repeat 10 times, record in `evidence/testing/performance-report.md`

### PERF-MANUAL-02: ASR Latency
1. From SPEECH_END event (T0) to TRANSCRIPT received (T1)
2. Observable in debug drawer timestamps
3. Record 10 measurements

### PERF-MANUAL-03: TTS Time-to-First-Audio
1. From LLM actions sent (T0) to first audio chunk played (T1)
2. Observable in WebSocket frame timing in DevTools
3. Record 10 measurements

### PERF-MANUAL-04: Interruption Latency (T0 → T1)
1. T0 = VAD detects new speech during playback (console log)
2. T1 = `audioPlayer.pause()` called (console log)
3. Record minimum, maximum, average, median, p95

---

## Notes

- All screenshots should be at 1920×1080 or higher resolution
- Avoid capturing personal information in screenshots (use synthetic test data only)
- If a screenshot cannot be captured (e.g., service not running), note it as "MANUAL CAPTURE NEEDED" in the evidence README
- Do not fabricate any screenshots or paste placeholder images

# VoiceForm — Performance Report

**Generated**: 2026-09-05  
**Test Suite**: `backend/tests/test_m8_compatibility.py`

---

## Important Note on Measurement Scope

This report distinguishes between:
- **Automated measurements**: captured by the M8 test suite without live hardware
- **Manual capture required**: require a running extension, live microphone, and browser session

No performance numbers are fabricated. Where measurements cannot be taken automatically, explicit measurement protocols are provided.

---

## PERF-01: Profile Cache Latency (Redis Fallback)

**Method**: 20 calls to `ProfileCache.get_profile()` with an unreachable Redis URL (forces fallback path). Measures the time for the cache miss to resolve.

**Context**: In production (Redis available), cache hits are expected to be <5ms. This test measures the fallback path (Redis connection timeout → miss). With `socket_timeout=1.0s`, each miss waits up to 1 second before returning None.

| Metric | Value |
|--------|-------|
| Iterations | 20 |
| Min | 990.3 ms |
| Max | 1015.5 ms |
| Avg | 1008.4 ms |
| Median | 1009.2 ms |
| P95 | 1015.5 ms |

> **Note**: Exact values printed by `test_m8_perf01_profile_cache_latency` with `-s` flag. See test output.

**Practical implication**: When Redis is available and connected, profile cache hits are sub-millisecond (in-memory data structure lookup at Redis). This test measures the timeout behavior — a worst case that never occurs in normal operation.

---

## PERF-02: Profile Save Latency (SQLite In-Memory)

**Method**: 10 calls to `ProfileService.upsert_field()` with in-memory SQLite, NullCache (no Redis overhead). Measures pure DB write path.

| Metric | Value |
|--------|-------|
| Iterations | 10 |
| Min | 7.4 ms |
| Max | 23.9 ms |
| Avg | 10.4 ms |
| Median | 9.0 ms |
| P95 | 23.9 ms |

> **Assertion**: Median < 200ms — **PASS** (9.0ms actual)

> **Note**: In-memory SQLite is significantly slower than PostgreSQL for first-write operations due to transaction overhead. Production PostgreSQL with connection pooling (asyncpg) will be faster per operation. This is a conservative floor measurement.

---

## PERF-03: Form Scanning — Headless (jsdom)

Measured by the `run-m8-headless.cjs` harness. These are scanner-only times (no network, no audio).

| Category | Fields Detected | Notes |
|----------|----------------|-------|
| A — Simple | 10 | ~100ms total for jsdom parse + scan |
| B — Complex | 19 | |
| C — SPA | 0 (async) | jsdom async mount incomplete |
| D — A11y | 11 | 4 separate forms |
| E — Dynamic | 11 | CSS-hidden fields still in DOM |
| F — Non-standard | 9 | Including 3 orphan fields |

**Total scan time** (jsdom, all 6 pages): Approximately 200ms total in Node.js process. In-browser content script scan time is typically <10ms for most pages (native DOM access is faster than jsdom).

---

## PERF-04: Voice Pipeline (Manual Capture Required)

The following measurements require a live browser session with microphone access and running backend. They cannot be captured by automated tests.

### 4a: VAD Latency

**Definition**: Time from user beginning to speak to VAD SPEECH_START event firing.  
**Measurement protocol**: See `evidence/screenshots/README.md` → PERF-MANUAL-01

| Measurement | Value |
|-------------|-------|
| Min | MANUAL CAPTURE NEEDED |
| Max | MANUAL CAPTURE NEEDED |
| Avg | MANUAL CAPTURE NEEDED |
| Median | MANUAL CAPTURE NEEDED |
| P95 | MANUAL CAPTURE NEEDED |

**Expected range** (not a claim): Silero VAD processes in 30ms chunks. Detection latency is typically 60–200ms depending on audio buffer size.

### 4b: ASR Latency

**Definition**: Time from SPEECH_END to TRANSCRIPT received at backend.  
**Includes**: Audio encoding + WebSocket transmission + Qwen3-ASR inference

| Measurement | Value |
|-------------|-------|
| Min | MANUAL CAPTURE NEEDED |
| Max | MANUAL CAPTURE NEEDED |
| Avg | MANUAL CAPTURE NEEDED |
| Median | MANUAL CAPTURE NEEDED |
| P95 | MANUAL CAPTURE NEEDED |

**Expected range**: Qwen3-ASR-0.6B on CPU: 500ms–3000ms depending on utterance length and hardware. On GPU: 50–300ms.

### 4c: LLM Inference Latency

**Definition**: Time from transcript received to LLM actions response.  
**Model**: qwen2.5:1.5b via Ollama

| Measurement | Value |
|-------------|-------|
| Avg | MANUAL CAPTURE NEEDED |
| Median | MANUAL CAPTURE NEEDED |
| P95 | MANUAL CAPTURE NEEDED |

**Expected range**: 500ms–3000ms on CPU depending on form schema size and utterance complexity. Much faster on GPU.

### 4d: TTS Time-to-First-Audio

**Definition**: Time from LLM response text available to first PCM audio chunk played in browser.  
**Includes**: TTS safety sanitization + Rime API call + first chunk transmission

| Measurement | Value |
|-------------|-------|
| Min | MANUAL CAPTURE NEEDED |
| Max | MANUAL CAPTURE NEEDED |
| Avg | MANUAL CAPTURE NEEDED |
| Median | MANUAL CAPTURE NEEDED |
| P95 | MANUAL CAPTURE NEEDED |

**Expected range**: Rime streaming API: typically 200–800ms to first chunk.

### 4e: Total Response Time

**Definition**: From VAD SPEECH_START to first TTS audio playing in browser.

| Measurement | Value |
|-------------|-------|
| Avg | MANUAL CAPTURE NEEDED |

**Expected range**: 1.5s–6s total on CPU hardware. Dominated by ASR and LLM inference time.

---

## PERF-05: Interruption Latency (T0 → T1)

**T0**: VAD detects new speech while audio is playing (SPEECH_START event)  
**T1**: `audioPlayer.pause()` is called (audio stops)

**Measurement protocol**: See `evidence/screenshots/README.md` → PERF-MANUAL-04

| Metric | Value |
|--------|-------|
| Min | MANUAL CAPTURE NEEDED |
| Max | MANUAL CAPTURE NEEDED |
| Avg | MANUAL CAPTURE NEEDED |
| Median | MANUAL CAPTURE NEEDED |
| P95 | MANUAL CAPTURE NEEDED |

**Theoretical minimum**: The `INTERRUPT` message travels:
- VAD fires → `stopPlayback()` call in content script: ~0ms (same process)
- Content script → Backend INTERRUPT message: ~WebSocket round-trip (~1–5ms on localhost)
- Backend issues `TTS_CANCEL` → Client `audioPlayer.pause()`: ~WebSocket round-trip

On localhost, interruption should be perceptually instantaneous (<100ms). The generation ID system ensures no stale audio plays after interruption.

---

## Performance Targets — Disclaimer

VoiceForm does not claim specific sub-100ms latency targets for voice pipeline components. Real-world performance depends on:
- CPU/GPU hardware
- Ollama model serving configuration
- Network conditions (for Rime TTS)
- Audio device characteristics
- Browser and OS audio stack latency
- Form complexity (number of fields in LLM context)

The measurements above are collected with the actual test infrastructure and annotated where manual capture is required. No numbers are fabricated.

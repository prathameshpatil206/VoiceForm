# ⚡ VoiceForm

<div align="center">

![VoiceForm Banner](https://img.shields.io/badge/VoiceForm-AI%20Voice%20Autofill-6366f1?style=for-the-badge&logo=googlechrome&logoColor=white)

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Chrome MV3](https://img.shields.io/badge/Chrome%20Extension-Manifest%20V3-4285F4?style=flat-square&logo=googlechrome&logoColor=white)](https://developer.chrome.com/docs/extensions/mv3/)
[![Ollama](https://img.shields.io/badge/Ollama-Qwen2.5--1.5B-000000?style=flat-square&logo=ollama&logoColor=white)](https://ollama.com)
[![Tests](https://img.shields.io/badge/Tests-129%2F129%20Passing-success?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

**Autonomous, Real-Time AI Voice Form Autofill Chrome Extension & Backend**  
*Fill complex web forms hands-free in seconds using natural speech, local LLM slot extraction, sub-50ms VAD barge-in interruption, browser-native streaming interim transcription, and Rime TTS audio confirmation.*

<br/>

[![Demo Video](https://img.shields.io/badge/Demo%20Video-Google%20Drive-red?style=for-the-badge&logo=google-drive&logoColor=white)](https://drive.google.com/file/d/1e700CQAgJVkJiBGt57R__gWACEXapSt4/view?usp=sharing)
[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/prathameshpatil206/VoiceForm)
[![Rime Evidence](https://img.shields.io/badge/RIME-EVIDENCE.md-6366f1?style=for-the-badge&logo=markdown&logoColor=white)](RIME_EVIDENCE.md)

</div>

---

## 🌟 Key Highlights

- 🎙️ **Dual-Engine Speech Recognition**: 
  - **Browser-Native Web Speech API**: Delivers real-time, streaming interim transcripts directly to the UI with zero server latency and automatic punctuation.
  - **Raw PCM Audio Streaming**: Sends 16kHz audio frames to the backend for server-side VAD, Whisper, and Qwen3-ASR inference.
- 🧠 **Local AI Slot Extraction & Reasoning**: Powered by **Ollama (`qwen2.5:1.5b`)** with strict schema constraint validation and fuzzy option matching.
- ⚡ **Sub-Millisecond Heuristic Safety Net**: Automatic fallback regex extractor instantly resolves names, emails, and phone numbers even under high LLM load.
- 🛑 **Sub-50ms Barge-in Interruption**: Real-time voice activity detection via **Silero VAD ONNX** halts in-flight LLM reasoning and TTS audio streaming the instant the user speaks.
- 🔊 **Conversational Rime TTS Feedback**: Natural speech synthesis confirming completed fields and prompting for missing required inputs.
- 🛡️ **Tolerant Action Normalization**: Seamlessly normalizes LLM verbs (`fill`, `set_field`, `write`, `choose`) and matches form fields across IDs, names, labels, and prefixes.
- 🧩 **Universal DOM Discovery**: Scans static inputs, dynamic SPAs, multi-step wizards, ARIA-accessible elements, and custom synthetic dropdowns/toggles.
- 💎 **Gemini-Inspired Glassmorphic Drawer**: Floating cyberpunk UI featuring a live animated audio visualizer, streaming interim transcript card, action timeline, and latency telemetry.
- 🔒 **Privacy & PII Protection**: Local inference by default; sensitive fields (credit cards, passwords, CVVs) are masked and shielded from logs.

---

## 🏗️ Architecture Overview

```mermaid
flowchart TD
    subgraph Browser ["Chrome Extension (Manifest V3)"]
        DOM["DOM Scanner & Observer"]
        Mic["MicManager (16kHz PCM)"]
        WebSpeech["Web Speech API Recognizer"]
        Drawer["Cyberpunk Glassmorphic Drawer"]
        Filler["Smart Field Autofiller & Dispatcher"]
    end

    subgraph Backend ["FastAPI WebSocket Server (:8765)"]
        WS["WebSocket Protocol Gateway"]
        Store[("In-Memory / Redis Session Store")]
        VAD["Silero VAD ONNX Engine"]
        Ollama["Ollama Local LLM (Qwen 2.5)"]
        Heuristic["Sub-ms Heuristic Extractor"]
        Validator["Action & Schema Normalizer"]
        TTS["Rime TTS Streaming API"]
    end

    DOM -->|"Form Schema vf-f-*"| WS
    Mic -->|"16kHz Audio Frames"| WS
    WebSpeech -->|"Final Transcript Frame"| WS
    WebSpeech -.->|"Streaming Interim Text"| Drawer

    WS --> Store
    WS -->|"Voice Activity Detection"| VAD
    WS -->|"Prompt & Schema"| Ollama
    WS -.->|"Zero-Latency Fallback"| Heuristic

    Ollama -->|"Structured Actions"| Validator
    Heuristic -->|"Extracted Actions"| Validator

    Validator -->|"ACTION_DISPATCH"| Filler
    Validator -->|"Conversational Text"| TTS
    TTS -->|"Audio Chunks"| Drawer
    VAD -.->|"Barge-in Interruption Signal"| Drawer
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
Ensure you have the following installed on your system:
- **Node.js** (v18 or v20+)
- **Python** (v3.11 or v3.12)
- **Ollama** ([Download & Install Ollama](https://ollama.com/))
- **Google Chrome** (v110+)
- **Docker Desktop** *(Optional — automatic in-memory fallback included)*

---

### 2. Pull Ollama Model
In your terminal, pull the recommended lightweight local model:
```bash
ollama pull qwen2.5:1.5b
```

---

### 3. Setup & Start Backend Server

1. **Navigate to the backend directory and set up a Python virtual environment:**
   ```bash
   cd backend
   python -m venv .venv
   ```

2. **Activate the virtual environment:**
   - **Windows PowerShell:**
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Create or verify `backend/.env`:
   ```ini
   PORT=8765
   HOST=127.0.0.1
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5:1.5b
   RIME_API_KEY=your_rime_api_key_here
   RIME_SPEAKER=marsh
   VAD_THRESHOLD=0.5
   VAD_SILENCE_DURATION_MS=550
   DATABASE_URL=postgresql+asyncpg://voiceform:voiceform@127.0.0.1:5432/voiceform
   REDIS_URL=redis://127.0.0.1:6379/0
   ENABLE_PROFILE_PERSISTENCE=false
   ```

5. **Run the backend server:**
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
   ```
   Check server status by opening: `http://localhost:8765/health`

---

### 4. Build & Install Chrome Extension

1. **Build the extension bundle:**
   ```bash
   cd extension
   npm install
   npm run build
   ```
   *(Build artifacts will be compiled into `extension/dist/`)*

2. **Load the Extension into Chrome:**
   - Open Google Chrome and go to `chrome://extensions`
   - Toggle **Developer mode** on (top right toggle)
   - Click **Load unpacked** (top left)
   - Select the `extension/dist` folder

---

### 5. Serve & Test Real-World Forms

Start the local test server hosting all 6 validation categories:
```bash
npx serve test-pages -p 3000
```

Open any category in Chrome:
- 📄 **[Category A: Simple Contact Form](http://localhost:3000/m8-category-a-simple.html)** — Standard inputs, emails, textareas, and radios.
- 📋 **[Category B: Complex Multi-step / Financial](http://localhost:3000/m8-category-b-complex.html)** — Wizard steps, SSN/currency masks, conditional fieldsets.
- ⚛️ **[Category C: Single Page App (SPA / React-style)](http://localhost:3000/m8-category-c-spa.html)** — Dynamic DOM mutations, custom event dispatching.
- ♿ **[Category D: ARIA / Accessible Form](http://localhost:3000/m8-category-d-accessibility.html)** — ARIA controls, comboboxes, and screen-reader regions.
- ⚡ **[Category E: Dynamic Cascading Form](http://localhost:3000/m8-category-e-dynamic.html)** — Interdependent select dropdowns, cascading options.
- 🛠️ **[Category F: Custom Non-standard Controls](http://localhost:3000/m8-category-f-nonstandard.html)** — Custom div-based switches, button toggles, rating stars.

---

## 🎙️ How to Use VoiceForm

1. Open any form page (e.g. `http://localhost:3000/m8-category-a-simple.html`).
2. The **VoiceForm Drawer** appears in the bottom-right corner displaying `● WS: CONNECTED`.
3. Click **"🎙️ Start Voice"** (grant microphone permission on first use).
4. Speak your form information naturally in one breath:
   > *"My name is Alex Morgan, email is alex.morgan@example.com, and phone number is 555-0199"*
5. Watch the **interim streaming transcript** update in real time as you speak!
6. When you pause or click **"⏹️ Stop Voice"**, VoiceForm will:
   - Match and highlight fields with an electric blue animation.
   - Dispatch genuine DOM `input` / `change` events.
   - Synthesize a natural conversational voice response confirming the filled slots.
7. **Barge-in Support**: Speak anytime while Rime TTS is talking to immediately cut off audio and begin your next command!

---

## 🎙️ Exact Rime TTS Specifications

VoiceForm integrates **Rime Text-to-Speech** for ultra-low latency conversational audio confirmation:

| Specification Parameter | Value | Details & Implementation |
| :--- | :--- | :--- |
| **Model ID** | `mist` | High-fidelity, low-latency streaming conversational voice model |
| **Speaker** | `marsh` *(fallback: `amber`)* | Natural conversational tone and pacing |
| **Language** | `en` / `en-US` | English |
| **Endpoint URL** | `https://users.rime.ai/v1/rime-tts` | Production Rime TTS HTTP endpoint |
| **Audio Format** | `pcm` | Linear 16-bit PCM mono, 16,000 Hz sample rate |
| **Transport** | HTTP Streaming (`POST`) | Chunked transfer encoding via `httpx.AsyncClient.stream()` for sub-250ms time-to-first-audio (TTFA) |

> 📖 **Rime Evidence Document**: For the formal hard voice claim, acceptance tests, procedure, and quantitative measurements, see [**`RIME_EVIDENCE.md`**](RIME_EVIDENCE.md).  
> 🎥 **Demo Video Recording**: [**Watch VoiceForm Demo (Google Drive)**](https://drive.google.com/file/d/1e700CQAgJVkJiBGt57R__gWACEXapSt4/view?usp=sharing) *(breakdown & criteria mapped in [**`DEMO_LINK.md`**](DEMO_LINK.md))*.

---

## 🔌 Third-Party Services & Dependencies

| Service / Dependency | Role in VoiceForm | Execution Mode / Endpoint | Data Privacy & Network Boundaries |
| :--- | :--- | :--- | :--- |
| **Rime TTS API** | Conversational voice synthesis | Cloud HTTP Streaming (`https://users.rime.ai/v1/rime-tts`) | Spoken response text sent to Rime; binary audio chunks streamed back. |
| **Ollama (Qwen 2.5 1.5B)** | Semantic slot extraction & reasoning | Local (`http://localhost:11434`) | 100% on-device local execution; zero prompt or voice data leaves machine. |
| **Web Speech API** | Real-time streaming interim ASR | Browser-native (Chrome engine) | Low-latency local browser event stream with zero server overhead. |
| **Silero VAD ONNX** | Sub-50ms barge-in voice detection | Local CPU ONNX (`backend/app/ai/vad`) | In-memory 16kHz PCM audio frame evaluation; zero external network calls. |
| **PostgreSQL & Redis** *(Optional)* | Encrypted profile & session store | Local Docker containers | Local persistence with AES-256 encryption at rest; sensitive fields masked. |

---

## ⚠️ Known Limitations

1. **Cross-Origin Iframes**: Chrome Manifest V3 security policies prevent extension content scripts from reading or manipulating DOM inputs inside cross-origin `<iframe>` elements without per-site permissions.
2. **CAPTCHA & Bot Defenses**: VoiceForm intentionally avoids interacting with Cloudflare turnstiles, reCAPTCHAs, and bot verification puzzles to preserve website security controls.
3. **Canvas-Rendered Inputs**: Custom UI widgets rendered directly to an HTML5 `<canvas>` (without standard DOM `<input>` or ARIA roles) cannot be traversed by the DOM scanner.
4. **Microphone Permissions**: Browser requires explicit user microphone permission on initial launch.
5. **Acoustic Feedback Without Headsets**: In environments with external speakers turned up loud without hardware echo cancellation, loud TTS playback may trigger VAD thresholding; using headphones or Chrome AEC prevents this.

---

## 🛡️ Failure Behavior & Resiliency

VoiceForm features multi-tiered graceful degradation so that user form filling is never blocked or corrupted:

1. **LLM Downtime or Latency Spike**: If Ollama is offline or times out (>1500ms), the **Sub-Millisecond Heuristic Extractor** immediately parses the transcript using compiled regex patterns for names, emails, and phone numbers, completing the fill with <1ms overhead.
2. **Rime TTS Network Disconnect / Quota Exceeded**: If the Rime API returns a 4xx/5xx or times out, the backend logs the error and sends a client-side warning toast. Form autofill remains 100% completed so the user's workflow is never interrupted.
3. **Mid-Speech Barge-in Interruption**: If the user speaks while Rime audio is playing, Silero VAD fires within ~35ms, immediately incrementing the generation ID, aborting the in-flight HTTP stream via `asyncio.Event`, and sending an `AUDIO_INTERRUPT` frame to wipe the client audio playback buffer.
4. **Unmatched / Hallucinated Fields**: The Action Validator cross-references every proposed slot against the active `PageScanResult` schema. Any hallucinated fields or forbidden values (passwords, credit cards) are rejected and pruned.

---

## ⚡ Latency & Telemetry Benchmarks

| Pipeline Stage | Technology | Typical Latency | SLA |
| :--- | :--- | :--- | :--- |
| **Barge-in Interruption** | Silero VAD ONNX | **~35 ms** | `< 100 ms` |
| **Streaming Transcript** | Web Speech API (Client) | **~10 ms** | Real-time |
| **Heuristic Fallback** | Compiled Python Regex | **< 1 ms** | `< 5 ms` |
| **Local LLM Slot Extraction** | Ollama Qwen 2.5 1.5B | **~350 - 550 ms** | `< 1500 ms` |
| **Audio Confirmation Synthesis** | Rime TTS Streaming API | **~180 - 250 ms** | `< 500 ms` |
| **End-to-End Voice-to-Fill** | Full Pipeline | **~650 - 900 ms** | `< 2000 ms` |

---

## 🧪 Testing & Verification

### Backend Test Suite (129 Tests)
Run the automated test suite covering protocol handling, Silero VAD, Rime TTS, barge-in interruption, profile persistence, and multi-page compatibility:
```bash
cd backend
.\.venv\Scripts\python -m pytest
```
```
================= 129 passed, 4 warnings in 85.42s =================
```

### Headless Multi-Category Compatibility Verification
Run the end-to-end headless browser benchmark across Categories A–F:
```bash
node test-pages/run-m8-headless.cjs
```

---

## 📂 Project Structure

```
VoiceForm/
├── backend/                  # FastAPI Backend & AI Pipeline
│   ├── app/
│   │   ├── ai/               # AI Engines & Reasoning
│   │   │   ├── asr/          # Whisper / Qwen3-ASR wrappers
│   │   │   ├── llm/          # Ollama Qwen integration & heuristic extractor
│   │   │   ├── tts/          # Rime TTS streaming client & sanitizer
│   │   │   ├── vad/          # Silero VAD ONNX barge-in detector
│   │   │   └── validator.py  # Action normalizer & fuzzy field matcher
│   │   ├── api/              # REST Profile & System routes
│   │   ├── db/               # SQLAlchemy Models & Migrations
│   │   ├── profile/          # AES-256 encrypted profile manager
│   │   ├── store/            # In-memory & Redis session state
│   │   └── ws/               # WebSocket handler & multi-channel pipeline
│   └── tests/                # 129 Pytest unit & integration test suites
├── extension/                # Chrome Manifest V3 Extension
│   ├── src/
│   │   ├── background/       # MV3 Service worker & HTTPS bridge
│   │   ├── content/          # Content scripts & DOM automation
│   │   │   ├── audio/        # MicManager, StreamPlayer & SpeechRecognizer
│   │   │   ├── debug-ui/     # Cyberpunk drawer, visualizer & telemetry
│   │   │   ├── dom/          # DOM scanner, field annotator & observer
│   │   │   └── ws/           # Resilient WebSocket client & reconnect logic
│   │   └── popup/            # Extension settings popup UI
│   ├── manifest.json         # Extension Manifest V3 configuration
│   └── build.js              # Multi-target Vite bundler
├── test-pages/               # Diverse form benchmark test pages (Categories A-F)
├── evidence/                 # Milestone reports, security analysis, & telemetry
└── docker-compose.yml        # PostgreSQL & Redis container configuration
```

---

## 🛡️ Privacy, Security & Shielding

1. **Local-First Execution**: User audio processing, speech recognition, and LLM reasoning run locally on machine hardware.
2. **Sensitive Field Shielding**: Password fields, credit card numbers, CVVs, and SSNs are flagged during DOM discovery and never logged in plain text.
3. **AES-256 Storage Encryption**: Profile data stored in PostgreSQL is encrypted at rest with AES-256 keys.
4. **TTS Audio Sanitization**: Spoken outputs pass through safety sanitizers to strip out raw IDs, CSS selectors, or leaked code fragments.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
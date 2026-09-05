# ⚡ VoiceForm

> **AI-Powered Real-Time Voice Form Autofill Chrome Extension & Backend**  
> Fill out complex web forms hands-free in seconds using natural speech, local LLM reasoning, sub-100ms VAD interruption, and Rime TTS audio confirmation.

---

## 🌟 Key Highlights

- 🎙️ **Natural Voice Input**: Speak freely without structured syntax (*"My name is Alex Morgan, email is alex@example.com, and phone is 555-0199"*).
- 🧠 **Local AI Reasoning**: Powered by **Ollama (`qwen2.5:1.5b`)** with strict schema validation & fuzzy option matching.
- ⚡ **Real-Time Voice Activity Detection (VAD)**: Sub-50ms interruption detection using **Silero VAD ONNX**.
- 🔊 **Rime TTS Confirmation**: Conversational audio feedback synthesized using **Rime TTS API**.
- 🧩 **Generic DOM Discovery**: Automatically scans static, dynamic, multi-step, ARIA-accessible, and SPA forms.
- 🔒 **Encrypted User Profiles**: AES-256 encrypted persistence in **PostgreSQL** with fast **Redis** caching and in-memory fallback.

---

## 🏗️ Architecture Overview

```mermaid
graph TD
    Browser[Chrome Extension MV3] -->|1. Real-time Audio / JSON Schema| WS[WebSocket Server :8765]
    WS -->|2. Voice Activity Detection| VAD[Silero VAD ONNX]
    WS -->|3. Speech Recognition| ASR[In-Memory Whisper / Qwen3-ASR]
    WS -->|4. Slot Extraction & Validation| LLM[Ollama Local LLM]
    WS -->|5. Voice Feedback| TTS[Rime TTS Streaming API]
    WS -->|6. Profile Persistence| DB[(PostgreSQL + Redis)]
    WS -->|7. Targeted Fill Actions| Browser
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
Ensure you have the following installed:
- **Node.js** (v18+)
- **Python** (v3.11 or v3.12)
- **Ollama** ([Download Ollama](https://ollama.com/))
- **Docker Desktop** *(Optional - automatic in-memory fallback included)*

---

### 2. Setup Ollama (Local LLM)
In a terminal, pull the model:
```bash
ollama pull qwen2.5:1.5b
```

---

### 3. Setup & Start Backend Server

1. Navigate to the backend directory and create a virtual environment:
   ```bash
   cd backend
   python -m venv .venv
   ```

2. Activate the virtual environment:
   - **Windows PowerShell**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux**:
     ```bash
     source .venv/bin/activate
     ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create your `.env` file in `backend/.env`:
   ```ini
   PORT=8765
   HOST=127.0.0.1
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5:1.5b
   RIME_API_KEY=your_rime_api_key_here
   RIME_SPEAKER=marsh
   DATABASE_URL=postgresql+asyncpg://voiceform:voiceform@127.0.0.1:5432/voiceform
   REDIS_URL=redis://127.0.0.1:6379/0
   ```

5. *(Optional)* Start PostgreSQL & Redis via Docker:
   ```bash
   docker-compose up -d
   ```
   *(If Docker is not running, VoiceForm automatically uses its built-in in-memory fallback store.)*

6. Start the backend:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
   ```
   Verify health by visiting: `http://localhost:8765/health`

---

### 4. Build & Load the Chrome Extension

1. Build the extension bundle:
   ```bash
   cd extension
   npm install
   npm run build
   ```

2. Load in Google Chrome:
   - Open Chrome and navigate to `chrome://extensions`
   - Enable **Developer mode** (top right)
   - Click **Load unpacked** (top left)
   - Select the `extension/dist` folder

---

### 5. Serve & Test Form Pages

Run a local test server with diverse form layouts:
```bash
npx serve test-pages -p 3000
```

Open any category test page in Chrome:
- 📄 **[Category A: Simple Contact Form](http://localhost:3000/m8-category-a-simple.html)**
- 📋 **[Category B: Complex Multi-step / Financial](http://localhost:3000/m8-category-b-complex.html)**
- ⚛️ **[Category C: Single Page App (SPA / React-style)](http://localhost:3000/m8-category-c-spa.html)**
- ♿ **[Category D: ARIA / Accessible Form](http://localhost:3000/m8-category-d-accessibility.html)**
- ⚡ **[Category E: Dynamic Cascading Form](http://localhost:3000/m8-category-e-dynamic.html)**
- 🛠️ **[Category F: Custom Non-standard Controls](http://localhost:3000/m8-category-f-nonstandard.html)**

---

## 🎙️ How to Use

1. Navigate to any web page with form fields.
2. The **VoiceForm Drawer** will appear in the bottom-right corner showing `● WS: CONNECTED`.
3. Click **"🎙️ Start Voice"** (grant microphone permissions if prompted).
4. Speak your form details naturally:
   > *"My name is Alex Morgan, email is alex.morgan@example.com, and phone number is 555-0199"*
5. Click **"⏹️ Stop Voice"** or pause for ~800ms.
6. The fields will highlight in blue and populate instantly with real-time audio confirmation!

---

## 🧪 Running Automated Tests

Run the complete backend test suite (128 passing unit & integration tests):
```bash
cd backend
.\.venv\Scripts\python -m pytest
```

Run headless browser form-filling compatibility verification:
```bash
node test-pages/run-m8-headless.cjs
```

---

## 📂 Project Structure

```
VoiceForm/
├── backend/                  # FastAPI WebSocket & AI Pipeline
│   ├── app/
│   │   ├── ai/               # ASR, LLM, TTS (Rime), VAD (Silero), & Validators
│   │   ├── api/              # REST Profile Endpoints
│   │   ├── db/               # SQLAlchemy Models & Migrations
│   │   ├── profile/          # User Profile AES-256 Storage & Redis Caching
│   │   └── ws/               # Real-time WebSocket Protocol & Handlers
│   └── tests/                # 128 Unit & Integration Test Suites
├── extension/                # Chrome MV3 Extension
│   ├── src/
│   │   ├── background/       # MV3 Service Worker
│   │   ├── content/          # DOM Scanner, Mic Manager, Filler, Debug Drawer
│   │   └── popup/            # Extension Popup UI
│   └── manifest.json         # Extension Manifest V3
├── test-pages/               # Real-world form compatibility test pages (A-F)
├── evidence/                 # Architecture, Security, Privacy & Reliability Reports
└── docker-compose.yml        # PostgreSQL & Redis container configuration
```

---

## 🛡️ Privacy & Security

- **Local Inference**: Speech and form reasoning execute locally on your machine via Ollama & Whisper.
- **Client-Side VAD**: Audio is processed in memory; no audio recordings are permanently stored on disk.
- **AES-256 Profile Encryption**: User profile values stored at rest are encrypted with application keys.
- **Sensitive Field Shielding**: Credit cards, passwords, and CVVs are masked and excluded from persistent logging.

---

## 📄 License
MIT License. Created for the VoiceForm Hackathon.
# 🎥 VoiceForm — Demo Video & Submission Metadata

## 🔗 Submission Links for Judges

- 🎥 **Demo Video Recording (Google Drive)**: [Watch VoiceForm Demo (4-5 mins)](https://drive.google.com/file/d/1e700CQAgJVkJiBGt57R__gWACEXapSt4/view?usp=sharing)
- 🐙 **GitHub Repository**: [https://github.com/prathameshpatil206/VoiceForm](https://github.com/prathameshpatil206/VoiceForm)
- ⏱️ **Duration**: ~4–5 minutes
- 📦 **Submission Package**: `VoiceForm_Submission.zip`

---

## ⏱️ Video Breakdown & Requirements Coverage

This recording demonstrates all mandatory criteria required by the hackathon organizers:

| Timestamp | Segment | Demonstrated Behavior | Organizer Requirement |
| :--- | :--- | :--- | :--- |
| **0:00 – 0:40** | **Target User & Problem** | Explains the frustration of repetitive form-filling; hands-free accessibility for complex web workflows. | *Target user and problem* |
| **0:40 – 1:30** | **Active Speech Provider & End-to-End Flow** | Shows the dual-engine speech provider (browser-native Web Speech API for real-time streaming interim transcripts + 16kHz PCM audio streaming to backend). | *Speech provider active & normal end-to-end flow* |
| **1:30 – 2:10** | **Form Filling & Rime TTS Feedback** | AI extracts slots using local Ollama (`qwen2.5:1.5b`) and fills DOM inputs with dispatch events; Rime TTS speaks natural conversational audio confirmation. | *Normal end-to-end flow & speech synthesis* |
| **2:10 – 3:15** | **Hard Voice Problem & Deliberate Stress Case** | **Sub-50ms Barge-in Interruption**: User intentionally interrupts mid-speech while Rime TTS is speaking. Audio stream cuts off instantly; generation ID is incremented; stale audio queue is flushed with zero bleed-over. | *Selected hard voice problem & deliberate stress/failure case* |
| **3:15 – 3:50** | **Safety Guard & Heuristic Fallback** | Shows prohibited candidate rejection (passwords/credit cards never saved or spoken) and sub-millisecond regex heuristic safety net. | *Failure behavior & safety* |
| **3:50 – 4:30** | **Results & Measurements** | Summarizes measured telemetry: ~35ms VAD latency, <50ms audio cut-off, ~215ms TTFA, 129/129 test suite pass. | *Result or measurement* |

---

## 🔍 How Judges Can Reproduce the Behavior

1. Follow the quickstart instructions in [README.md](README.md).
2. Run the repeatable fixture:
   ```bash
   .\backend\.venv\Scripts\python scripts/verify_rime.py
   ```
3. Run the full automated test suite:
   ```bash
   cd backend && .\.venv\Scripts\python -m pytest
   ```
4. Test live in browser on `http://localhost:3000/m8-category-a-simple.html`.

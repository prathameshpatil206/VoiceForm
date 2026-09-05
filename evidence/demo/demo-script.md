# VoiceForm — Hackathon Demo Script

**Duration**: 2–4 minutes  
**Format**: Live demonstration with narration

---

## Pre-Demo Setup Checklist

Before presenting, verify:
- [ ] `docker-compose up -d` (PostgreSQL + Redis running)
- [ ] `cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8765` running
- [ ] `ollama serve` and `ollama run qwen2.5:1.5b` loaded
- [ ] Extension loaded in Chrome via Load Unpacked → `extension/dist/`
- [ ] Test page open: `http://localhost:3000/m8-category-a-simple.html`
- [ ] Microphone permissions granted to extension
- [ ] Browser volume at a comfortable level

---

## Demo Script

---

### [0:00 — OPENING]

**Narrate:**

> "Every day, people fill out the same information on dozens of different forms — their name, email, phone number, address — over and over again.
>
> What if you could just… say it?
>
> This is VoiceForm."

---

### [0:20 — STEP 1: Form Detection]

**Action**: Point to the open form page. Open the VoiceForm debug drawer (bottom of page) or popup.

**Narrate:**

> "VoiceForm is a Chrome extension that scans any web form automatically — no per-site configuration required."

**Action**: Show the scan result in the debug drawer.

**Narrate:**

> "On this page, VoiceForm has detected 10 fields — first name, last name, email, phone, address, city, state, postal code, website, and message. It identified each field's semantic label without any setup."

---

### [0:45 — STEP 2: Voice Input]

**Action**: Click the VoiceForm microphone button. Speak clearly:

> *"My name is Pratham Test, my email is pratham dot test at example dot com, and my phone number is five five five zero one zero one two three four."*

**Narrate:**

> "I simply speak naturally — I don't have to click each field."

---

### [1:05 — STEP 3: AI Interpretation]

**Action**: Show the debug drawer — transcript and extracted actions are visible.

**Narrate:**

> "Qwen — our local AI — converts my speech into structured actions. It understood 'Pratham Test' maps to first name and last name, and the email and phone were correctly identified."

---

### [1:20 — STEP 4: Automatic Filling]

**Action**: The form fields fill automatically.

**Narrate:**

> "VoiceForm fills the fields using framework-compatible DOM events — the same technique that works on React, Vue, and plain HTML forms."

---

### [1:35 — STEP 5: Conversational Response]

**Action**: Audio plays from the assistant.

**Narrate:**

> "The assistant generates a natural response and Rime TTS speaks it aloud. It sounds like a real conversation, not a robotic list of confirmations."

---

### [1:50 — STEP 6: Follow-Up Question]

**Narrate:**

> "VoiceForm notices that several fields — address, city, state — are still empty. It asks me for the missing information."

*The assistant audio says something like: "I've filled in your name, email, and phone. Could you tell me your address and city?"*

---

### [2:05 — STEP 7: Interruption]

**Action**: While the assistant is still speaking, start speaking:

> *"Wait — my city is Hubli."*

**Narrate:**

> "While the assistant is still speaking, I interrupt naturally."

**Action**: Show that audio stops immediately. The new utterance is processed.

**Narrate:**

> "The audio stops within milliseconds. VoiceForm uses a generation ID system — the old response is invalidated the moment my new voice is detected. No stale audio plays after the interruption."

---

### [2:30 — STEP 8: Profile Persistence]

**Action**: Close the tab and navigate back to the same form URL.

**Narrate:**

> "Now I'll reload the page — completely fresh session."

**Action**: Activate VoiceForm. The previously spoken fields auto-suggest or can be recalled.

**Narrate:**

> "VoiceForm remembers my name and email from the previous session — stored in PostgreSQL with Redis caching for fast retrieval. I don't have to repeat myself."

---

### [2:50 — STEP 9: Safety]

**Action**: Open the form and point to a password field (or navigate to a registration form).

**Narrate:**

> "VoiceForm is smart about what it saves. Passwords, credit card numbers, OTPs — these are never stored. The safety guard runs before any persistence operation, with explicit key and value pattern checks.
>
> You can see in our security tests — 13 security items verified — passwords, CVV codes, JWTs, API keys — all blocked at the persistence layer."

---

### [3:10 — TECHNICAL HIGHLIGHTS]

**Narrate:**

> "Let me highlight the technical stack:
>
> - Chrome MV3 extension with a generic DOM scanner — no per-site configuration
> - Framework-compatible DOM filler using native value setters — works with React and Vue
> - FastAPI WebSocket backend for real-time bidirectional communication
> - Silero VAD for voice activity detection
> - Qwen3-ASR for speech recognition — running locally
> - Qwen LLM via Ollama — local inference, your voice stays on your machine
> - Rime TTS for natural spoken responses
> - A generation ID system that makes interruption seamless
> - PostgreSQL + Redis for persistent, fast profile storage"

---

### [3:35 — CLOSING]

**Narrate:**

> "VoiceForm works on any public web form that allows content scripts. We've validated it across six categories of forms — simple, complex, SPA-rendered, accessibility-heavy, dynamic, and non-standard patterns.
>
> Form filling doesn't have to be a chore. VoiceForm makes it a conversation."

---

## Demo Variations

### Short Version (60 seconds)
- Step 1 (form detection) — 10s
- Step 2 + 4 (speak + fill) — 30s
- Step 5 (TTS response) — 10s
- Step 7 (interruption) — 10s

### Technical Deep Dive
Add between Step 3 and Step 4:
- Show the WebSocket message log
- Show the raw LLM JSON actions
- Show the action validator rejecting a field that doesn't exist on the page

---

## Potential Questions and Answers

**Q: Does this work on any website?**  
A: It works on any website where Chrome allows content scripts — same-origin pages and cross-origin top-level frames. Cross-origin iframes are a browser security restriction we respect.

**Q: Is my voice sent to the cloud?**  
A: Voice audio is processed locally by our ASR model. The only cloud call is for TTS — and only the assistant's spoken text goes there, not your voice.

**Q: What happens to my profile data?**  
A: It's stored locally in your PostgreSQL instance. You can view and delete it via REST API. Passwords and payment information are never stored.

**Q: Does VoiceForm submit forms automatically?**  
A: No. VoiceForm fills fields but never submits. You remain in control.

**Q: What about CAPTCHAs?**  
A: VoiceForm does not interact with CAPTCHAs — they are a security control we intentionally leave alone.

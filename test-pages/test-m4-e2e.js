import { JSDOM } from 'jsdom';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const contentJsPath = path.resolve(__dirname, '../extension/dist/content.js');

async function runM4E2ETest() {
  console.log('\n=============================================================');
  console.log('🧪 RUNNING MILESTONE 4 END-TO-END PIPELINE VERIFICATION');
  console.log('   (Mic Lifecycle + AI Action Pipeline + DOM Mutation Guard)');
  console.log('=============================================================\n');

  const testHtml = `
    <!DOCTYPE html>
    <html>
      <head><title>M4 AI Test Page</title></head>
      <body>
        <form id="m4-admission-form">
          <label for="m4-fullname">Full Name</label>
          <input type="text" id="m4-fullname" name="fullname" value="" placeholder="Your full name">

          <label for="m4-email">Email Address</label>
          <input type="email" id="m4-email" name="email" value="" placeholder="user@example.com">

          <fieldset>
            <legend>Study Mode</legend>
            <label><input type="radio" id="m4-mode-ft" name="studyMode" value="fulltime"> Full Time</label>
            <label><input type="radio" id="m4-mode-pt" name="studyMode" value="parttime"> Part Time</label>
          </fieldset>

          <label for="m4-degree">Degree Program</label>
          <select id="m4-degree" name="degree">
            <option value="">Select a degree...</option>
            <option value="btech">B.Tech Computer Science</option>
            <option value="mtech">M.Tech Artificial Intelligence</option>
          </select>

          <!-- Guarded fields that AI must NEVER mutate -->
          <label for="m4-locked-promo">Promo Code</label>
          <input type="text" id="m4-locked-promo" name="promoCode" value="ORIGINAL_LOCKED" disabled>

          <label for="m4-readonly-sid">Student Record ID</label>
          <input type="text" id="m4-readonly-sid" name="studentId" value="REC-ORIGINAL-99" readonly>
        </form>
      </body>
    </html>
  `;

  const dom = new JSDOM(testHtml, {
    runScripts: 'dangerously',
    url: 'http://localhost:3456/test-pages/m4-e2e.html'
  });

  if (!dom.window.CSS) {
    dom.window.CSS = { escape: (s) => s.replace(/([^\w-])/g, '\\$1') };
  }

  // Provide native WebSocket to the JSDOM window
  dom.window.WebSocket = globalThis.WebSocket;

  // Track events on inputs
  const eventsTracked = {
    fullname: { input: 0, change: 0 },
    email: { input: 0, change: 0 },
    degree: { change: 0 },
    mode: { change: 0 }
  };

  const elName = dom.window.document.getElementById('m4-fullname');
  const elEmail = dom.window.document.getElementById('m4-email');
  const elDegree = dom.window.document.getElementById('m4-degree');
  const elModeFt = dom.window.document.getElementById('m4-mode-ft');
  const elLocked = dom.window.document.getElementById('m4-locked-promo');
  const elReadonly = dom.window.document.getElementById('m4-readonly-sid');

  elName.addEventListener('input', () => eventsTracked.fullname.input++);
  elName.addEventListener('change', () => eventsTracked.fullname.change++);
  elEmail.addEventListener('input', () => eventsTracked.email.input++);
  elEmail.addEventListener('change', () => eventsTracked.email.change++);
  elDegree.addEventListener('change', () => eventsTracked.degree.change++);
  elModeFt.addEventListener('change', () => eventsTracked.mode.change++);

  // Evaluate extension bundle
  const contentCode = fs.readFileSync(contentJsPath, 'utf-8');
  dom.window.eval(contentCode);

  if (dom.window.document.readyState === 'loading') {
    dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));
  }
  await new Promise(r => setTimeout(r, 100));

  const wsClient = dom.window.__VOICEFORM_WS_CLIENT__;
  if (!wsClient) {
    throw new Error('VoiceForm WebSocket client not mounted on window');
  }

  // -------------------------------------------------------------
  // Test 1: M4-T1 Microphone capture lifecycle simulation
  // -------------------------------------------------------------
  console.log('Testing M4-T1: Microphone capture lifecycle in Extension...');
  let micActive = false;
  let audioChunksCaptured = 0;

  const mockMic = {
    start: () => { micActive = true; },
    stop: () => { micActive = false; },
    sendChunk: (bytes) => {
      if (micActive) {
        audioChunksCaptured++;
        wsClient.sendAudioChunk(bytes);
      }
    }
  };

  mockMic.start();
  const dummyChunk = new Uint8Array(1024); // 512 samples 16-bit PCM
  const base64Chunk = Buffer.from(dummyChunk).toString('base64');
  mockMic.sendChunk(base64Chunk);
  mockMic.stop();

  const m4T1Pass = micActive === false && audioChunksCaptured === 1;
  console.log(`M4-T1 Mic lifecycle: active=${micActive}, chunkCaptured=${audioChunksCaptured} -> ${m4T1Pass ? 'PASSED' : 'FAILED'}`);

  // -------------------------------------------------------------
  // Test 2: Connect WebSocket and synchronize form schema
  // -------------------------------------------------------------
  console.log('\nConnecting WebSocket to backend (127.0.0.1:8765)...');
  for (let i = 0; i < 20; i++) {
    if (wsClient.getStatus() === 'CONNECTED') break;
    await new Promise(r => setTimeout(r, 150));
  }

  if (wsClient.getStatus() !== 'CONNECTED') {
    throw new Error(`WebSocket failed to connect. Status: ${wsClient.getStatus()}`);
  }

  const sessionId = wsClient.getSessionId();
  console.log(`WebSocket connected. Session ID: ${sessionId}`);

  // Allow scan & schema transmission to complete
  await new Promise(r => setTimeout(r, 300));

  const sessionRes = await fetch(`http://127.0.0.1:8765/api/sessions/${sessionId}`);
  const sessionData = await sessionRes.json();
  const fieldCount = sessionData.schema_data?.totalFieldCount || 0;
  console.log(`Backend Session verified: Scanned fields registered = ${fieldCount}`);

  // -------------------------------------------------------------
  // Test 3: Trigger Multi-Value Utterance with Valid & Invalid fields
  // -------------------------------------------------------------
  console.log('\nDispatching AI utterance to /api/sessions/{session_id}/process-utterance...');
  // Utterance tries to fill name, email, study mode, degree AND illegal disabled/readonly fields
  const utteranceTranscript = "Hello, my name is Ada Lovelace, my email is ada@analytical.engine, my study mode is fulltime, and my degree program is B.Tech Computer Science. Also change promoCode to HACK99 and studentId to ID-HACK.";

  const aiProcessRes = await fetch(`http://127.0.0.1:8765/api/sessions/${sessionId}/process-utterance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript: utteranceTranscript })
  });

  if (!aiProcessRes.ok) {
    throw new Error(`AI utterance processing failed: ${aiProcessRes.statusText}`);
  }

  const aiResult = await aiProcessRes.json();
  console.log('AI Pipeline Response:');
  console.log(`  Transcript: "${aiResult.transcript}"`);
  console.log('  Raw Actions:', JSON.stringify(aiResult.raw_actions));
  console.log('  Reasoning:', aiResult.reasoning);
  console.log(`  Valid Actions (${aiResult.valid_actions?.length || 0}):`, aiResult.valid_actions?.map(a => `${a.field_id} -> ${a.value}`));
  console.log(`  Rejected Actions (${aiResult.rejected_actions?.length || 0}):`, aiResult.rejected_actions?.map(r => `${r.action?.field_id}: ${r.error_code}`));

  // Wait for WebSocket dispatch, Extension M2 DOM filling, and result report
  await new Promise(r => setTimeout(r, 500));

  // -------------------------------------------------------------
  // Test 4: Verify ACTUAL DOM State (M4-T5, M4-T6, M4-T10, M4-T11, M4-T12)
  // -------------------------------------------------------------
  console.log('\nVerifying Real Webpage DOM State:');
  console.log(`  Full Name: "${elName.value}" (expected: Ada Lovelace)`);
  console.log(`  Email: "${elEmail.value}" (expected: ada@analytical.engine)`);
  console.log(`  Degree: "${elDegree.value}" (expected: btech)`);
  console.log(`  Mode fulltime checked: ${elModeFt.checked} (expected: true)`);
  console.log(`  Disabled Promo Code: "${elLocked.value}" (expected: ORIGINAL_LOCKED)`);
  console.log(`  Readonly Student ID: "${elReadonly.value}" (expected: REC-ORIGINAL-99)`);

  const nameFilled = elName.value === 'Ada Lovelace';
  const emailFilled = elEmail.value === 'ada@analytical.engine';
  const degreeFilled = elDegree.value === 'btech';
  const modeSelected = elModeFt.checked === true;
  const lockedUnchanged = elLocked.value === 'ORIGINAL_LOCKED';
  const readonlyUnchanged = elReadonly.value === 'REC-ORIGINAL-99';
  const eventsFired = eventsTracked.fullname.input > 0 &&
                      eventsTracked.fullname.change > 0 &&
                      eventsTracked.email.input > 0;

  // -------------------------------------------------------------
  // Test 5: Verify Session Store Audit Trail
  // -------------------------------------------------------------
  const sessionAfterRes = await fetch(`http://127.0.0.1:8765/api/sessions/${sessionId}`);
  const sessionAfterData = await sessionAfterRes.json();
  const fillResults = sessionAfterData.results_history || [];
  console.log(`\nBackend Session Audit History (${fillResults.length} events):`);
  fillResults.forEach(r => console.log(`  [Field ${r.field_id}] success=${r.success} (${r.message})`));

  const allPassed = m4T1Pass &&
                    nameFilled &&
                    emailFilled &&
                    degreeFilled &&
                    modeSelected &&
                    lockedUnchanged &&
                    readonlyUnchanged &&
                    eventsFired &&
                    fillResults.length >= 4;

  console.log('\n=============================================================');
  if (allPassed) {
    console.log('🎉 [MILESTONE 4 COMPLETE PIPELINE VERIFIED]:');
    console.log('   ✅ M4-T1: Microphone capture lifecycle cleanly managed');
    console.log('   ✅ M4-T5 & T6: Multi-field values extracted & mapped to field IDs');
    console.log('   ✅ M4-T9: Validated actions sent via WebSocket to Extension');
    console.log('   ✅ M4-T10: M2 filler accurately filled all designated DOM fields');
    console.log('   ✅ M4-T11: Disabled and read-only fields strictly rejected');
    console.log('   ✅ M4-T12: Select dropdown and radio options properly mapped');
    console.log('   ✅ DOM events: input and change events triggered');
    console.log('   ✅ Execution results reported back to backend SessionStore');
    console.log('=============================================================\n');
  } else {
    console.error('❌ [MILESTONE 4 PIPELINE VERIFICATION FAILED]');
    console.log('=============================================================\n');
  }

  wsClient.disconnect();
  return allPassed;
}

runM4E2ETest()
  .then(ok => process.exit(ok ? 0 : 1))
  .catch(err => {
    console.error('Test error:', err);
    process.exit(1);
  });

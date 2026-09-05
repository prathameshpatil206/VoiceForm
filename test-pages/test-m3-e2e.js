import { JSDOM } from 'jsdom';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const contentJsPath = path.resolve(__dirname, '../extension/dist/content.js');

async function runM3E2ETest() {
  console.log('\n==================================================');
  console.log('🧪 RUNNING M3 T6 END-TO-END COMPLETE PATH VERIFICATION');
  console.log('==================================================\n');

  const testHtml = `
    <!DOCTYPE html>
    <html>
      <head><title>E2E Form</title></head>
      <body>
        <form id="e2e-form">
          <label for="e2e-username">Full Name</label>
          <input type="text" id="e2e-username" name="username" value="" placeholder="Your full name">

          <label for="e2e-email">Email Address</label>
          <input type="email" id="e2e-email" name="userEmail" value="" placeholder="email@example.com">
        </form>
      </body>
    </html>
  `;

  const dom = new JSDOM(testHtml, {
    runScripts: 'dangerously',
    url: 'http://localhost:3456/test-pages/e2e.html'
  });

  if (!dom.window.CSS) {
    dom.window.CSS = { escape: (s) => s.replace(/([^\w-])/g, '\\$1') };
  }

  // Provide native WebSocket to the JSDOM window
  dom.window.WebSocket = globalThis.WebSocket;

  // Track events on input
  let inputEventCount = 0;
  let changeEventCount = 0;
  const elUser = dom.window.document.getElementById('e2e-username');
  elUser.addEventListener('input', () => inputEventCount++);
  elUser.addEventListener('change', () => changeEventCount++);

  // Evaluate the real extension content script
  const contentCode = fs.readFileSync(contentJsPath, 'utf-8');
  dom.window.eval(contentCode);

  if (dom.window.document.readyState === 'loading') {
    dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));
  }
  await new Promise(r => setTimeout(r, 100));

  const wsClient = dom.window.__VOICEFORM_WS_CLIENT__;
  if (!wsClient) {
    throw new Error('WebSocket client not initialized on window');
  }

  // 1. Wait for connection to establish
  console.log('Waiting for WebSocket connection to FastAPI backend (127.0.0.1:8765)...');
  for (let i = 0; i < 20; i++) {
    if (wsClient.getStatus() === 'CONNECTED') break;
    await new Promise(r => setTimeout(r, 150));
  }

  const isConnected = wsClient.getStatus() === 'CONNECTED';
  const sessionId = wsClient.getSessionId();
  console.log(`Connection Status: ${wsClient.getStatus()}, Session ID: ${sessionId}`);

  if (!isConnected) {
    throw new Error(`Failed to connect to WebSocket server. Status=${wsClient.getStatus()}`);
  }

  // 2. Wait 300ms for FORM_SCHEMA to be transmitted and stored
  await new Promise(r => setTimeout(r, 300));

  // 3. Verify backend received schema
  const sessionRes = await fetch(`http://127.0.0.1:8765/api/sessions/${sessionId}`);
  if (!sessionRes.ok) {
    throw new Error(`Failed to query session from backend: ${sessionRes.statusText}`);
  }
  const sessionData = await sessionRes.json();
  const schemaReceived = sessionData.schema_data !== null;
  const fieldsCount = sessionData.schema_data?.totalFieldCount;
  console.log(`Backend Session verified: Schema fields received = ${fieldsCount}`);

  // 4. Send FILL_ACTION from backend to extension
  console.log('Dispatching FILL_ACTION from backend to extension over WebSocket...');
  const triggerRes = await fetch(`http://127.0.0.1:8765/api/sessions/${sessionId}/trigger-fill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: {
        action: 'fill_field',
        field_id: 'e2e-username',
        value: 'Ada Lovelace'
      }
    })
  });

  if (!triggerRes.ok) {
    throw new Error(`Failed to trigger fill from backend: ${triggerRes.statusText}`);
  }

  // 5. Wait for extension to receive, fill via M2, and report result back
  await new Promise(r => setTimeout(r, 400));

  // 6. Verify ACTUAL DOM state in the webpage
  const finalDomValue = elUser.value;
  console.log(`Final DOM element value: "${finalDomValue}"`);
  console.log(`Dispatched events: input=${inputEventCount}, change=${changeEventCount}`);

  // 7. Verify backend received and recorded the execution result
  const sessionAfterRes = await fetch(`http://127.0.0.1:8765/api/sessions/${sessionId}`);
  const sessionAfterData = await sessionAfterRes.json();
  const resultsRecorded = sessionAfterData.results_history || [];
  const latestResult = resultsRecorded[resultsRecorded.length - 1];
  console.log(`Backend recorded FillResult: success=${latestResult?.success}, message="${latestResult?.message}"`);

  const t6Pass = finalDomValue === 'Ada Lovelace' &&
                 inputEventCount > 0 &&
                 changeEventCount > 0 &&
                 latestResult?.success === true &&
                 schemaReceived === true;

  console.log('\n--------------------------------------------------');
  if (t6Pass) {
    console.log('✅ [T6 COMPLETE PATH PASSED]:');
    console.log('   1. Extension scanned DOM (#e2e-username)');
    console.log('   2. Extension transmitted schema to FastAPI');
    console.log('   3. Backend received & stored schema');
    console.log('   4. Backend dispatched FILL_ACTION over WebSocket');
    console.log('   5. Extension received FILL_ACTION');
    console.log('   6. M2 Filler mutated actual DOM element to "Ada Lovelace"');
    console.log('   7. Synthetic input and change events fired');
    console.log('   8. Extension transmitted FILL_RESULT back to backend');
    console.log('   9. Backend recorded execution outcome in SessionStore');
  } else {
    console.error('❌ [T6 COMPLETE PATH FAILED]');
  }
  console.log('--------------------------------------------------\n');

  wsClient.disconnect();
  return t6Pass;
}

runM3E2ETest()
  .then(ok => process.exit(ok ? 0 : 1))
  .catch(err => {
    console.error('Test error:', err);
    process.exit(1);
  });

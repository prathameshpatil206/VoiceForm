import { PageScanResult } from '../types/schema';
import { MicrophoneManager } from './audio/mic-manager';
import { AudioStreamPlayer } from './audio/stream-player';
import { VoiceFormDebugDrawer } from './debug-ui/debug-drawer';
import { executeFillAction, executeFillActions } from './filler/dom-filler';
import { FormAction, FillResult } from './filler/types';
import { scanPageForms } from './scanner/form-scanner';
import { FormMutationWatcher } from './scanner/mutation-watcher';
import { VoiceFormWebSocketClient } from './ws/ws-client';

export interface InterruptionRecord {
  generationId: number;
  timestampT0: number; // moment user speech detected
  timestampT1: number; // moment audio playback stopped
  latencyMs: number;
  reason: string;
}

let currentScanResult: PageScanResult | null = null;
let debugDrawer: VoiceFormDebugDrawer | null = null;
let mutationWatcher: FormMutationWatcher | null = null;
let wsClient: VoiceFormWebSocketClient | null = null;
let micManager: MicrophoneManager | null = null;
let audioPlayer: AudioStreamPlayer | null = null;
const interruptionHistory: InterruptionRecord[] = [];

function performScan(): PageScanResult {
  currentScanResult = scanPageForms();
  if (debugDrawer) {
    debugDrawer.updateScanResult(currentScanResult);
  }
  // If WebSocket is active, synchronize schema to backend
  if (wsClient && wsClient.getStatus() === 'CONNECTED') {
    wsClient.sendSchema(currentScanResult);
  }
  // Store or cache last scan in window for headless testing access
  (window as any).__VOICEFORM_SCAN_RESULT__ = currentScanResult;
  return currentScanResult;
}

export function fillField(action: FormAction): FillResult {
  const result = executeFillAction(action, currentScanResult || undefined);
  // Re-scan after DOM modification to keep schema in sync
  performScan();
  return result;
}

export function fillFields(actions: FormAction[]): FillResult[] {
  const results = executeFillActions(actions, currentScanResult || undefined);
  performScan();
  return results;
}

export async function toggleVoice(): Promise<void> {
  if (!micManager) return;
  if (micManager.getIsRecording()) {
    micManager.stopListening();
    debugDrawer?.setVoiceState('idle');
  } else {
    // If currently speaking, stop speech first
    if (audioPlayer && audioPlayer.isPlaying()) {
      stopPlayback('toggle_voice');
    }
    debugDrawer?.setTranscript('');
    debugDrawer?.setExtractedActions([]);
    debugDrawer?.setAiError('');
    debugDrawer?.setAskUser('');
    const started = await micManager.startListening();
    if (started) {
      debugDrawer?.setVoiceState('listening');
    }
  }
}

/**
 * Halts current audio playback immediately, invalidates active generation,
 * records interruption latency (T1 - T0), and sends INTERRUPT / TTS_CANCEL.
 */
export function stopPlayback(reason = 'explicit_stop', t0Timestamp?: number): number {
  const t0 = t0Timestamp || performance.now();
  let latencyMs = 0;

  if (audioPlayer && audioPlayer.isPlaying()) {
    const activeGen = audioPlayer.getGenerationId() ?? wsClient?.getActiveGenerationId() ?? 0;
    const reqId = audioPlayer.getRequestId();

    const t1 = audioPlayer.stop();
    latencyMs = Math.max(0, t1 - t0);

    const record: InterruptionRecord = {
      generationId: activeGen,
      timestampT0: t0,
      timestampT1: t1,
      latencyMs,
      reason
    };
    interruptionHistory.push(record);
    (window as any).__VOICEFORM_INTERRUPTIONS__ = interruptionHistory;
    (window as any).__VOICEFORM_LAST_INTERRUPT_LATENCY__ = latencyMs;

    debugDrawer?.recordInterruption(latencyMs);

    if (wsClient && wsClient.getStatus() === 'CONNECTED') {
      wsClient.sendInterrupt(activeGen, reason, t0);
      if (reqId) {
        wsClient.sendTtsCancel(reqId, activeGen);
      }
    }
    return latencyMs;
  }
  return 0;
}

function init(): void {
  // Ensure we don't inject multiple times
  if ((window as any).__VOICEFORM_INITIALIZED__) return;
  (window as any).__VOICEFORM_INITIALIZED__ = true;

  // Initial Scan
  performScan();

  // Initialize UI Drawer with rescan, sample fill, voice toggle, and stop audio handlers
  debugDrawer = new VoiceFormDebugDrawer(
    () => {
      performScan();
    },
    (action) => {
      return fillField(action);
    },
    () => {
      toggleVoice();
    },
    () => {
      stopPlayback('manual_button_click');
    }
  );

  // Initialize Audio Stream Player (M5 + M6)
  audioPlayer = new AudioStreamPlayer({
    onPlaybackStarted: (genId) => {
      debugDrawer?.setVoiceState('speaking');
      if (genId !== undefined) {
        debugDrawer?.setGenerationId(genId);
      }
    },
    onPlaybackComplete: (_genId) => {
      debugDrawer?.setVoiceState('idle');
    },
    onPlaybackStopped: (_genId) => {
      debugDrawer?.setVoiceState('idle');
    },
    onError: (err) => {
      console.error('[VoiceForm Content] Audio player error:', err);
      debugDrawer?.setAiError(`Audio error: ${err.message}`);
    }
  });

  // Initialize Microphone Manager (M4 + M6)
  micManager = new MicrophoneManager({
    sampleRate: 16000,
    speechThreshold: 0.025,
    onSpeechActivity: (t0Timestamp, _rms) => {
      // Real-time Interruption Detection: If audio is currently playing and user speaks
      if (audioPlayer && audioPlayer.isPlaying()) {
        console.log('⚡ [VoiceForm Interruption] User speech detected during assistant playback!');
        stopPlayback('vad_user_speech_interruption', t0Timestamp);
        debugDrawer?.setVoiceState('listening');
      }
    },
    onAudioChunk: (chunkBase64, _timestamp) => {
      if (wsClient && wsClient.getStatus() === 'CONNECTED') {
        wsClient.sendAudioChunk(chunkBase64);
      }
    },
    onAudioComplete: (audioBase64, durationMs) => {
      if (wsClient && wsClient.getStatus() === 'CONNECTED') {
        wsClient.sendAudio(audioBase64, durationMs);
      }
      debugDrawer?.setVoiceState('processing');
    },
    onError: (err) => {
      debugDrawer?.setVoiceState('error');
      debugDrawer?.setAiError(err.message || 'Microphone error');
    },
    onStateChange: (state) => {
      if (state === 'listening' && (!audioPlayer || !audioPlayer.isPlaying())) {
        debugDrawer?.setVoiceState('listening');
      }
    }
  });

  // Initialize WebSocket Client (M3 + M4 + M5 + M6)
  wsClient = new VoiceFormWebSocketClient({
    autoConnect: true,
    onStatusChange: (status) => {
      if (debugDrawer) {
        debugDrawer.updateWsStatus(status, wsClient?.getSessionId());
      }
    },
    onConnected: (_sid) => {
      const scan = currentScanResult || performScan();
      wsClient?.sendSchema(scan);
    },
    onGenerationStart: (payload) => {
      debugDrawer?.setGenerationId(payload.generation_id);
    },
    onGenerationCancelled: (payload) => {
      if (audioPlayer && audioPlayer.isPlaying()) {
        audioPlayer.stop();
      }
      debugDrawer?.setVoiceState('interrupted');
      debugDrawer?.setGenerationId(payload.generation_id);
    },
    onGenerationComplete: (payload) => {
      debugDrawer?.setGenerationId(payload.generation_id);
      debugDrawer?.setVoiceState('idle');
    },
    onTranscriptReceived: (transcript, _lang, genId) => {
      if (genId !== undefined) {
        debugDrawer?.setGenerationId(genId);
      }
      debugDrawer?.setTranscript(transcript);
      debugDrawer?.setVoiceState('processing');
    },
    onAiActionsReceived: (actions, genId) => {
      if (genId !== undefined) {
        debugDrawer?.setGenerationId(genId);
      }
      debugDrawer?.setExtractedActions(actions);
      debugDrawer?.setVoiceState('filling');
    },
    onAiResponseReceived: (response, genId) => {
      if (genId !== undefined) {
        debugDrawer?.setGenerationId(genId);
      }
      debugDrawer?.setAssistantResponse(response);
    },
    onTtsStart: (payload) => {
      const genId = payload.generation_id ?? wsClient?.getActiveGenerationId() ?? 0;
      audioPlayer?.startStream(payload.request_id, payload.format, payload.sample_rate, genId);
      debugDrawer?.setVoiceState('speaking');
      if (genId) {
        debugDrawer?.setGenerationId(genId);
      }
      if (payload.text) {
        debugDrawer?.setAssistantResponse(payload.text);
      }
    },
    onTtsAudio: (payload) => {
      const genId = payload.generation_id;
      audioPlayer?.playChunk(payload.audio_base64, payload.format, undefined, payload.is_final, genId);
    },
    onTtsEnd: (payload) => {
      const genId = payload.generation_id;
      audioPlayer?.endStream(payload.request_id, genId);
    },
    onTtsError: (payload) => {
      console.warn('[VoiceForm Content] TTS error:', payload);
      debugDrawer?.setAiError(`TTS Error: ${payload.message || payload.error_code}`);
      audioPlayer?.stop();
      debugDrawer?.setVoiceState('idle');
    },
    onTtsCancel: (payload) => {
      const genId = payload.generation_id;
      if (!genId || genId === audioPlayer?.getGenerationId()) {
        audioPlayer?.stop();
        debugDrawer?.setVoiceState('idle');
      }
    },
    onAskUserReceived: (question, genId) => {
      if (genId !== undefined) {
        debugDrawer?.setGenerationId(genId);
      }
      debugDrawer?.setAskUser(question);
      debugDrawer?.setVoiceState('idle');
    },
    onAiErrorReceived: (err) => {
      debugDrawer?.setAiError(err.message || err.code || 'AI Error');
      debugDrawer?.setVoiceState('error');
    },
    onFillActionReceived: (action, _genId) => {
      const res = fillField(action);
      debugDrawer?.setFillResults([res]);
      return res;
    },
    onFillActionsReceived: (actions, _genId) => {
      const results = fillFields(actions);
      debugDrawer?.setFillResults(results);
      return results;
    }
  });

  // Expose filler, mic manager, player, websocket API, and metrics globally for testing / headless integration
  (window as any).__VOICEFORM_FILL_FIELD__ = fillField;
  (window as any).__VOICEFORM_FILL_FIELDS__ = fillFields;
  (window as any).__VOICEFORM_WS_CLIENT__ = wsClient;
  (window as any).__VOICEFORM_MIC_MANAGER__ = micManager;
  (window as any).__VOICEFORM_AUDIO_PLAYER__ = audioPlayer;
  (window as any).__VOICEFORM_STOP_PLAYBACK__ = stopPlayback;
  (window as any).__VOICEFORM_TOGGLE_VOICE__ = toggleVoice;
  (window as any).__VOICEFORM_DEBUG_DRAWER__ = debugDrawer;
  (window as any).__VOICEFORM_INTERRUPTIONS__ = interruptionHistory;

  // Watch for dynamic DOM changes with debounced observer
  mutationWatcher = new FormMutationWatcher({
    debounceMs: 200,
    onUpdate: (result, latencyMs) => {
      currentScanResult = result;
      (window as any).__VOICEFORM_SCAN_RESULT__ = currentScanResult;
      (window as any).__VOICEFORM_LAST_LATENCY_MS__ = latencyMs;
      if (debugDrawer) {
        debugDrawer.updateScanResult(result, latencyMs);
      }
      if (wsClient && wsClient.getStatus() === 'CONNECTED') {
        wsClient.sendSchema(result);
      }
    }
  });
  mutationWatcher.start();

  // Listen for extension messages (from popup or background)
  if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (message.type === 'GET_PAGE_SCAN') {
        const result = currentScanResult || performScan();
        sendResponse({ success: true, data: result });
        return true;
      }
      if (message.type === 'TRIGGER_PAGE_SCAN') {
        const result = performScan();
        sendResponse({ success: true, data: result });
        return true;
      }
      if (message.type === 'EXECUTE_FILL_ACTION') {
        const result = fillField(message.action);
        sendResponse({ success: result.success, result });
        return true;
      }
      if (message.type === 'EXECUTE_FILL_ACTIONS') {
        const results = fillFields(message.actions);
        sendResponse({ success: results.every(r => r.success), results });
        return true;
      }
      if (message.type === 'STOP_AUDIO') {
        const latency = stopPlayback('extension_message');
        sendResponse({ success: true, latencyMs: latency });
        return true;
      }
      if (message.type === 'INTERRUPT') {
        const latency = stopPlayback('interrupt_command');
        sendResponse({ success: true, latencyMs: latency });
        return true;
      }
      if (message.type === 'GET_WS_STATUS') {
        sendResponse({
          status: wsClient?.getStatus() || 'DISCONNECTED',
          sessionId: wsClient?.getSessionId(),
          generationId: wsClient?.getActiveGenerationId() || 0,
          isPlaying: audioPlayer?.isPlaying() || false,
          interruptions: interruptionHistory
        });
        return true;
      }
      return false;
    });
  }
}

// Run when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

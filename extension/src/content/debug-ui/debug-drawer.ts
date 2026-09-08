import { FormField, PageScanResult } from '../../types/schema';
import { FormAction, FillResult } from '../filler/types';

export interface DrawerActionCallbacks {
  onRescan?: () => void;
  onFill?: (action: FormAction) => FillResult;
  onStartVoice?: () => void;
  onStopAndProcess?: () => void;
  onCancelVoice?: () => void;
  onStopPlayback?: () => void;
}

export class VoiceFormDebugDrawer {
  private host: HTMLElement | null = null;
  private shadow: ShadowRoot | null = null;
  private isOpen = false;
  private currentResult: PageScanResult | null = null;
  private lastLatencyMs: number | null = null;
  private highlightedElement: HTMLElement | null = null;
  private wsStatus: string = 'DISCONNECTED';
  private wsSessionId?: string;

  // Callbacks
  private onRescanRequested?: () => void;
  private onFillRequested?: (action: FormAction) => FillResult;
  private onStartVoiceRequested?: () => void;
  private onStopAndProcessRequested?: () => void;
  private onCancelVoiceRequested?: () => void;
  private onStopPlaybackRequested?: () => void;

  // Voice, AI, TTS & Interruption State
  private voiceStatus: 'idle' | 'listening' | 'processing' | 'filling' | 'speaking' | 'interrupted' | 'error' = 'idle';
  private latestTranscript: string = '';
  private extractedActions: FormAction[] = [];
  private fillResults: FillResult[] = [];
  private askUserQuestion: string = '';
  private aiErrorMessage: string = '';
  private assistantResponseText: string = '';
  private currentGenerationId = 0;
  private lastInterruptionLatencyMs: number | null = null;
  private interruptionCount = 0;

  // Cached DOM elements
  private bottomVoiceBtn: HTMLElement | null = null;
  private bottomVoiceIcon: HTMLElement | null = null;
  private bottomVoiceText: HTMLElement | null = null;
  private bottomCancelBtn: HTMLElement | null = null;
  private bottomLiveChipEl: HTMLElement | null = null;
  private bottomLiveTextEl: HTMLElement | null = null;
  private bottomPillEl: HTMLElement | null = null;
  private bottomDrawerBtn: HTMLElement | null = null;

  private drawerEl: HTMLElement | null = null;
  private headerVoiceBtn: HTMLElement | null = null;
  private headerVoiceIcon: HTMLElement | null = null;
  private headerVoiceText: HTMLElement | null = null;
  private headerCancelBtn: HTMLElement | null = null;
  private metaCountEl: HTMLElement | null = null;
  private metaGenEl: HTMLElement | null = null;
  private metaStateEl: HTMLElement | null = null;
  private metaWsEl: HTMLElement | null = null;
  private aiPanelEl: HTMLElement | null = null;
  private formsListEl: HTMLElement | null = null;

  constructor(
    onRescanOrCallbacks?: (() => void) | DrawerActionCallbacks,
    onFillRequested?: (action: FormAction) => FillResult,
    onVoiceToggleRequested?: () => void,
    onStopPlaybackRequested?: () => void
  ) {
    if (typeof onRescanOrCallbacks === 'object' && onRescanOrCallbacks !== null) {
      this.onRescanRequested = onRescanOrCallbacks.onRescan;
      this.onFillRequested = onRescanOrCallbacks.onFill;
      this.onStartVoiceRequested = onRescanOrCallbacks.onStartVoice;
      this.onStopAndProcessRequested = onRescanOrCallbacks.onStopAndProcess;
      this.onCancelVoiceRequested = onRescanOrCallbacks.onCancelVoice;
      this.onStopPlaybackRequested = onRescanOrCallbacks.onStopPlayback;
    } else {
      this.onRescanRequested = onRescanOrCallbacks;
      this.onFillRequested = onFillRequested;
      this.onStartVoiceRequested = onVoiceToggleRequested;
      this.onStopAndProcessRequested = onVoiceToggleRequested;
      this.onCancelVoiceRequested = onVoiceToggleRequested;
      this.onStopPlaybackRequested = onStopPlaybackRequested;
    }
    this.init();
  }

  private init(): void {
    if (document.querySelector('voiceform-debug-drawer')) return;

    this.host = document.createElement('voiceform-debug-drawer');
    this.shadow = this.host.attachShadow({ mode: 'open' });
    document.documentElement.appendChild(this.host);

    this.buildDOM();
    this.bindEvents();
    this.syncUI();
  }

  private buildDOM(): void {
    if (!this.shadow) return;

    this.shadow.innerHTML = `
      <style>
        :host {
          all: initial;
          font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif;
          font-size: 13px;
          line-height: 1.4;
          color: #e2e8f0;
          z-index: 2147483647;
          position: fixed;
          inset: 0;
          pointer-events: none;
          display: block;
        }

        * {
          box-sizing: border-box;
        }

        /* ── Smooth Gradient Movement Animations ── */
        @keyframes gradientFlow {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }

        @keyframes softBreathing {
          0%, 100% {
            transform: scale(1);
            box-shadow: 0 4px 16px rgba(239, 68, 68, 0.45);
          }
          50% {
            transform: scale(1.02);
            box-shadow: 0 4px 22px rgba(239, 68, 68, 0.65);
          }
        }

        @keyframes eqBarBounce {
          0%, 100% { height: 3px; }
          50% { height: 12px; }
        }

        @keyframes pulseDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.85); }
        }

        @keyframes spinRing {
          to { transform: rotate(360deg); }
        }

        /* ── Bottom Floating Controller Bar ── */
        .vf-bottom-bar {
          position: fixed;
          bottom: 18px;
          right: 18px;
          pointer-events: auto;
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 6px 8px 6px 14px;
          border-radius: 9999px;
          background: linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(30, 27, 75, 0.92), rgba(15, 23, 42, 0.94));
          background-size: 250% 250%;
          animation: gradientFlow 10s ease infinite;
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.14);
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45), 0 0 20px rgba(56, 189, 248, 0.15);
          user-select: none;
          transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s;
        }

        .vf-bottom-bar:hover {
          border-color: rgba(56, 189, 248, 0.35);
          box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55), 0 0 24px rgba(56, 189, 248, 0.25);
        }

        .vf-bottom-brand {
          display: flex;
          align-items: center;
          gap: 7px;
          font-weight: 700;
          font-size: 13px;
          color: #f8fafc;
          cursor: pointer;
        }

        .vf-brand-icon {
          color: #38bdf8;
          font-size: 15px;
          filter: drop-shadow(0 0 6px rgba(56, 189, 248, 0.5));
        }

        .vf-pill-badge {
          background: rgba(56, 189, 248, 0.15);
          color: #7dd3fc;
          padding: 2px 7px;
          border-radius: 9999px;
          font-size: 11px;
          font-weight: 600;
          border: 1px solid rgba(56, 189, 248, 0.25);
        }

        /* ── Simple & Clean Gradient Voice Button ── */
        .vf-voice-btn {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 14px;
          border-radius: 9999px;
          font-size: 12px;
          font-weight: 600;
          color: #ffffff;
          cursor: pointer;
          border: 1px solid rgba(255, 255, 255, 0.2);
          background: linear-gradient(135deg, #0284c7 0%, #2563eb 50%, #1d4ed8 100%);
          background-size: 200% 200%;
          animation: gradientFlow 6s ease infinite;
          box-shadow: 0 4px 14px rgba(2, 132, 199, 0.4);
          transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.25s ease;
          user-select: none;
        }

        .vf-voice-btn:hover {
          transform: translateY(-1px) scale(1.02);
          box-shadow: 0 6px 18px rgba(2, 132, 199, 0.6);
        }

        .vf-voice-btn:active {
          transform: translateY(0) scale(0.98);
        }

        /* Active Voice State - Listening: Vibrant Emerald/Cyan Stop & Fill */
        .vf-voice-btn.vf-btn-listening {
          background: linear-gradient(135deg, #059669 0%, #0d9488 50%, #0284c7 100%);
          background-size: 200% 200%;
          animation: gradientFlow 4s ease infinite, softBreathing 2s ease-in-out infinite;
          border-color: rgba(255, 255, 255, 0.4);
          box-shadow: 0 4px 20px rgba(16, 185, 129, 0.55);
        }

        /* Cancel Recording Button */
        .vf-cancel-btn {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 6px 11px;
          border-radius: 9999px;
          font-size: 11px;
          font-weight: 600;
          color: #fca5a5;
          cursor: pointer;
          border: 1px solid rgba(239, 68, 68, 0.35);
          background: rgba(239, 68, 68, 0.16);
          backdrop-filter: blur(10px);
          transition: all 0.15s ease;
          user-select: none;
        }

        .vf-cancel-btn:hover {
          background: rgba(239, 68, 68, 0.32);
          border-color: rgba(239, 68, 68, 0.55);
          color: #ffffff;
          transform: translateY(-1px);
        }

        .vf-cancel-btn:active {
          transform: translateY(0);
        }

        /* Live Interim Speech Transcript Chip (Gemini Style) */
        .vf-live-chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 11px;
          border-radius: 9999px;
          background: rgba(14, 165, 233, 0.15);
          border: 1px solid rgba(56, 189, 248, 0.35);
          color: #e0f2fe;
          font-size: 11px;
          font-weight: 500;
          max-width: 220px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          animation: pulseDot 2.5s infinite ease-in-out;
        }

        /* Active Voice State - Speaking */
        .vf-voice-btn.vf-btn-speaking {
          background: linear-gradient(135deg, #7c3aed 0%, #a855f7 50%, #6366f1 100%);
          background-size: 200% 200%;
          animation: gradientFlow 4s ease infinite;
          border-color: rgba(255, 255, 255, 0.35);
          box-shadow: 0 4px 20px rgba(168, 85, 247, 0.55);
        }

        /* Active Voice State - Processing */
        .vf-voice-btn.vf-btn-processing {
          background: linear-gradient(135deg, #d97706 0%, #f59e0b 50%, #b45309 100%);
          background-size: 200% 200%;
          animation: gradientFlow 3s ease infinite;
          border-color: rgba(255, 255, 255, 0.3);
          box-shadow: 0 4px 16px rgba(245, 158, 11, 0.45);
        }

        /* Soundwave bar equalizer */
        .vf-sound-eq {
          display: inline-flex;
          align-items: center;
          gap: 2px;
          height: 12px;
        }

        .vf-eq-bar {
          width: 2px;
          height: 12px;
          border-radius: 9999px;
          background: #ffffff;
          animation: eqBarBounce 0.7s ease-in-out infinite;
        }
        .vf-eq-bar:nth-child(1) { animation-delay: 0s; }
        .vf-eq-bar:nth-child(2) { animation-delay: 0.2s; }
        .vf-eq-bar:nth-child(3) { animation-delay: 0.4s; }

        /* Drawer Toggle Icon Button */
        .vf-icon-btn {
          background: rgba(255, 255, 255, 0.08);
          color: #94a3b8;
          border: 1px solid rgba(255, 255, 255, 0.12);
          width: 30px;
          height: 30px;
          border-radius: 50%;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .vf-icon-btn:hover {
          background: rgba(255, 255, 255, 0.16);
          color: #f8fafc;
          border-color: rgba(255, 255, 255, 0.25);
          transform: scale(1.05);
        }

        /* ── Sliding Inspector Drawer ── */
        .vf-drawer {
          position: fixed;
          top: 0;
          right: 0;
          bottom: 0;
          width: 480px;
          max-width: 92vw;
          pointer-events: auto;
          background: radial-gradient(circle at 10% 15%, rgba(99, 102, 241, 0.18) 0%, transparent 45%),
                      radial-gradient(circle at 90% 85%, rgba(236, 72, 153, 0.14) 0%, transparent 50%),
                      radial-gradient(circle at 50% 50%, rgba(14, 165, 233, 0.14) 0%, transparent 55%),
                      linear-gradient(135deg, #090d16 0%, #0f172a 50%, #0a0f1d 100%);
          background-size: 200% 200%;
          animation: gradientFlow 14s ease infinite;
          backdrop-filter: blur(28px);
          -webkit-backdrop-filter: blur(28px);
          border-left: 1px solid rgba(255, 255, 255, 0.12);
          box-shadow: -12px 0 40px rgba(0, 0, 0, 0.65);
          display: flex;
          flex-direction: column;
          transform: translateX(100%);
          transition: transform 0.26s cubic-bezier(0.16, 1, 0.3, 1), visibility 0.26s;
          visibility: hidden;
        }

        .vf-drawer.vf-drawer-open {
          transform: translateX(0);
          visibility: visible;
        }

        /* ── Header with Moving Gradient ── */
        .vf-header {
          padding: 16px 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          background: linear-gradient(90deg, rgba(15, 23, 42, 0.95), rgba(30, 27, 75, 0.88), rgba(15, 23, 42, 0.95));
          background-size: 200% 200%;
          animation: gradientFlow 10s ease infinite;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .vf-title {
          font-weight: 700;
          font-size: 15px;
          color: #f8fafc;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .vf-header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        /* Close cross button */
        .vf-close-btn {
          background: rgba(255, 255, 255, 0.08);
          color: #94a3b8;
          border: 1px solid rgba(255, 255, 255, 0.14);
          width: 32px;
          height: 32px;
          border-radius: 50%;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .vf-close-btn:hover {
          background: rgba(239, 68, 68, 0.25);
          border-color: rgba(239, 68, 68, 0.4);
          color: #fca5a5;
          transform: rotate(90deg);
        }

        /* ── Status Bar ── */
        .vf-meta {
          padding: 10px 20px;
          background: rgba(2, 6, 23, 0.55);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          font-size: 12px;
          color: #94a3b8;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        /* ── Body ── */
        .vf-body {
          padding: 18px 20px;
          overflow-y: auto;
          flex: 1;
        }

        .vf-section {
          margin-bottom: 18px;
        }

        .vf-section-header {
          font-size: 13px;
          font-weight: 600;
          color: #f1f5f9;
          margin-bottom: 9px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        /* AI Interaction Panel */
        .vf-ai-panel {
          background: rgba(15, 23, 42, 0.75);
          border: 1px solid rgba(56, 189, 248, 0.25);
          border-radius: 10px;
          padding: 14px;
          margin-bottom: 16px;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }

        .vf-transcript-box {
          background: rgba(0, 0, 0, 0.35);
          border-left: 3px solid #38bdf8;
          padding: 8px 12px;
          border-radius: 6px;
          margin-bottom: 8px;
          font-size: 12px;
        }

        .vf-response-box {
          background: rgba(139, 92, 246, 0.16);
          border-left: 3px solid #a855f7;
          padding: 8px 12px;
          border-radius: 6px;
          margin-bottom: 8px;
          font-size: 12px;
          color: #f3e8ff;
        }

        .vf-action-badge {
          display: inline-block;
          background: rgba(16, 185, 129, 0.2);
          border: 1px solid rgba(16, 185, 129, 0.35);
          color: #34d399;
          padding: 2px 7px;
          border-radius: 4px;
          font-size: 11px;
          margin: 2px;
        }

        .vf-field-card {
          background: rgba(15, 23, 42, 0.55);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          padding: 9px 12px;
          margin-bottom: 8px;
          transition: all 0.15s ease;
        }

        .vf-field-card:hover {
          border-color: rgba(56, 189, 248, 0.4);
          background: rgba(30, 41, 59, 0.65);
        }

        .vf-field-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 4px;
        }

        .vf-field-label {
          font-weight: 600;
          color: #f8fafc;
        }

        .vf-tag {
          font-size: 10px;
          font-weight: 700;
          padding: 1px 6px;
          border-radius: 4px;
          text-transform: uppercase;
        }

        .vf-tag-type { background: rgba(56, 189, 248, 0.2); color: #38bdf8; }
        .vf-tag-req { background: rgba(239, 68, 68, 0.2); color: #f87171; margin-left: 4px; }

        .vf-field-detail {
          font-size: 11px;
          color: #94a3b8;
          margin-top: 2px;
        }

        .vf-field-val {
          color: #34d399;
          font-weight: 600;
        }

        .vf-live-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          display: inline-block;
          animation: pulseDot 2s infinite ease-in-out;
        }

        .vf-spinner {
          width: 12px;
          height: 12px;
          border: 2px solid rgba(255, 255, 255, 0.2);
          border-top-color: #38bdf8;
          border-radius: 50%;
          animation: spinRing 0.8s linear infinite;
          display: inline-block;
        }
      </style>

      <!-- Bottom Floating Bar with Start/Stop Button & Field Count -->
      <div class="vf-bottom-bar" id="vf-bottom-bar">
        <div class="vf-bottom-brand" id="vf-brand-trigger" title="Click to toggle inspector">
          <span class="vf-brand-icon">⚡</span>
          <span>VoiceForm</span>
          <span class="vf-pill-badge" id="vf-bottom-pill">0 fields</span>
        </div>

        <!-- Live transcript chip (Gemini-style real-time speech feedback) -->
        <div class="vf-live-chip" id="vf-bottom-live-chip" style="display:none;" title="Listening...">
          <span>🎙️</span>
          <span id="vf-bottom-live-text" style="max-width:180px; overflow:hidden; text-overflow:ellipsis;"></span>
        </div>

        <!-- Primary Start / Stop Voice Button -->
        <button class="vf-voice-btn" id="vf-bottom-voice-btn" title="Start Voice Dictation">
          <span id="vf-bottom-voice-icon">🎙️</span>
          <span id="vf-bottom-voice-text">Start Voice</span>
          <div class="vf-sound-eq" id="vf-bottom-voice-eq" style="display:none;">
            <span class="vf-eq-bar"></span>
            <span class="vf-eq-bar"></span>
            <span class="vf-eq-bar"></span>
          </div>
        </button>

        <!-- Cancel recording button (only active while listening) -->
        <button class="vf-cancel-btn" id="vf-bottom-cancel-btn" style="display:none;" title="Cancel recording without filling">
          <span>✕</span>
          <span>Cancel</span>
        </button>

        <!-- Toggle drawer button -->
        <button class="vf-icon-btn" id="vf-bottom-drawer-btn" title="Toggle Form Inspector">📋</button>
      </div>

      <!-- Sliding Inspector Drawer with Moving Gradient Mesh -->
      <div class="vf-drawer" id="vf-drawer-el">
        <div class="vf-header">
          <div class="vf-title">
            <span style="color:#38bdf8;">⚡</span>
            <span>VoiceForm Inspector</span>
          </div>
          <div class="vf-header-actions">
            <!-- Header Start / Stop Voice Button -->
            <button class="vf-voice-btn" id="vf-header-voice-btn" title="Start Voice Dictation">
              <span id="vf-header-voice-icon">🎙️</span>
              <span id="vf-header-voice-text">Start Voice</span>
              <div class="vf-sound-eq" id="vf-header-voice-eq" style="display:none;">
                <span class="vf-eq-bar"></span>
                <span class="vf-eq-bar"></span>
                <span class="vf-eq-bar"></span>
              </div>
            </button>
            <!-- Header Cancel Button -->
            <button class="vf-cancel-btn" id="vf-header-cancel-btn" style="display:none;" title="Cancel recording without filling">
              <span>✕</span>
              <span>Cancel</span>
            </button>
            <!-- Cross button for closing drawer -->
            <button class="vf-close-btn" id="vf-close-btn" title="Close Inspector">✕</button>
          </div>
        </div>

        <div class="vf-meta">
          <div id="vf-meta-detected">
            <span>Detected: <strong>0</strong> form(s)</span>
          </div>
          <div style="display:flex; gap:10px; align-items:center;">
            <span style="font-weight:700; color: #38bdf8;" id="vf-meta-gen">
              Gen #0
            </span>
            <span style="display:inline-flex; align-items:center; gap:5px; font-weight:600;" id="vf-meta-state">
              <span class="vf-live-dot" style="background: #94a3b8"></span>
              <span>IDLE</span>
            </span>
            <span style="display:inline-flex; align-items:center; gap:5px; font-weight:600;" id="vf-meta-ws">
              <span class="vf-live-dot" style="background: #94a3b8"></span>
              <span>DISCONNECTED</span>
            </span>
          </div>
        </div>
        <div style="display:flex; gap:8px; align-items:center; font-size:11px; padding: 6px 16px 8px; border-bottom: 1px solid rgba(255,255,255,0.06); background: rgba(15,23,42,0.4); flex-wrap: wrap;">
          <span style="color:#94a3b8; font-weight:600;">Speech Provider:</span>
          <span class="vf-pill-badge" style="background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid rgba(56,189,248,0.3); font-size:10px; padding:2px 7px; border-radius:9999px;">🎙️ ASR: Web Speech API (Google) / Qwen3-ASR</span>
          <span class="vf-pill-badge" style="background:rgba(168,85,247,0.15); color:#c084fc; border:1px solid rgba(168,85,247,0.3); font-size:10px; padding:2px 7px; border-radius:9999px;">🔊 TTS: Rime API (Mist)</span>
        </div>

        <div class="vf-body">
          <div id="vf-ai-panel-container"></div>
          <div id="vf-forms-container">
            <div style="text-align: center; padding: 36px 16px; color: #64748b;">
              Navigate form fields or speak to autofill hands-free.
            </div>
          </div>
        </div>
      </div>
    `;

    // Cache elements for in-place updates
    this.bottomVoiceBtn = this.shadow.getElementById('vf-bottom-voice-btn');
    this.bottomVoiceIcon = this.shadow.getElementById('vf-bottom-voice-icon');
    this.bottomVoiceText = this.shadow.getElementById('vf-bottom-voice-text');
    this.bottomCancelBtn = this.shadow.getElementById('vf-bottom-cancel-btn');
    this.bottomLiveChipEl = this.shadow.getElementById('vf-bottom-live-chip');
    this.bottomLiveTextEl = this.shadow.getElementById('vf-bottom-live-text');
    this.bottomPillEl = this.shadow.getElementById('vf-bottom-pill');
    this.bottomDrawerBtn = this.shadow.getElementById('vf-bottom-drawer-btn');

    this.drawerEl = this.shadow.getElementById('vf-drawer-el');
    this.headerVoiceBtn = this.shadow.getElementById('vf-header-voice-btn');
    this.headerVoiceIcon = this.shadow.getElementById('vf-header-voice-icon');
    this.headerVoiceText = this.shadow.getElementById('vf-header-voice-text');
    this.headerCancelBtn = this.shadow.getElementById('vf-header-cancel-btn');
    this.metaCountEl = this.shadow.getElementById('vf-meta-detected');
    this.metaGenEl = this.shadow.getElementById('vf-meta-gen');
    this.metaStateEl = this.shadow.getElementById('vf-meta-state');
    this.metaWsEl = this.shadow.getElementById('vf-meta-ws');
    this.aiPanelEl = this.shadow.getElementById('vf-ai-panel-container');
    this.formsListEl = this.shadow.getElementById('vf-forms-container');
  }

  private bindEvents(): void {
    if (!this.shadow) return;

    // Primary voice button in bottom bar
    this.bottomVoiceBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.handlePrimaryVoiceClick();
    });

    // Cancel button in bottom bar
    this.bottomCancelBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.handleCancelVoiceClick();
    });

    // Primary voice button in header
    this.headerVoiceBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.handlePrimaryVoiceClick();
    });

    // Cancel button in header
    this.headerCancelBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.handleCancelVoiceClick();
    });

    // Toggle drawer via brand click or toggle button
    this.shadow.getElementById('vf-brand-trigger')?.addEventListener('click', () => {
      this.isOpen = !this.isOpen;
      this.syncDrawerVisibility();
    });

    this.bottomDrawerBtn?.addEventListener('click', () => {
      this.isOpen = !this.isOpen;
      this.syncDrawerVisibility();
    });

    // Cross button (✕) closes drawer
    this.shadow.getElementById('vf-close-btn')?.addEventListener('click', () => {
      this.isOpen = false;
      this.syncDrawerVisibility();
    });
  }

  private handlePrimaryVoiceClick(): void {
    if (this.voiceStatus === 'listening') {
      if (this.onStopAndProcessRequested) {
        this.onStopAndProcessRequested();
      }
    } else if (this.voiceStatus === 'speaking') {
      if (this.onStopPlaybackRequested) {
        this.onStopPlaybackRequested();
      }
    } else {
      // Idle, Error, Interrupted, or any other state
      if (this.onStartVoiceRequested) {
        this.onStartVoiceRequested();
      }
    }
  }

  private handleCancelVoiceClick(): void {
    if (this.onCancelVoiceRequested) {
      this.onCancelVoiceRequested();
    }
  }

  private syncDrawerVisibility(): void {
    if (!this.drawerEl) return;
    if (this.isOpen) {
      this.drawerEl.classList.add('vf-drawer-open');
      if (this.bottomDrawerBtn) this.bottomDrawerBtn.textContent = '✕';
    } else {
      this.drawerEl.classList.remove('vf-drawer-open');
      if (this.bottomDrawerBtn) this.bottomDrawerBtn.textContent = '📋';
    }
  }

  private syncUI(): void {
    this.syncVoiceStateUI();
    this.syncWsStatusUI();
    this.syncAiPanelUI();
    this.syncDrawerVisibility();
  }

  private syncVoiceStateUI(): void {
    const isListening = this.voiceStatus === 'listening';
    const isProcessing = this.voiceStatus === 'processing';
    const isSpeaking = this.voiceStatus === 'speaking';
    const isFilling = this.voiceStatus === 'filling';

    // Synchronize both buttons (Bottom bar button + Header button)
    const buttons = [this.bottomVoiceBtn, this.headerVoiceBtn];
    buttons.forEach((btn) => {
      if (!btn) return;
      btn.classList.remove('vf-btn-listening', 'vf-btn-speaking', 'vf-btn-processing');
      if (isListening) {
        btn.classList.add('vf-btn-listening');
      } else if (isSpeaking) {
        btn.classList.add('vf-btn-speaking');
      } else if (isProcessing || isFilling) {
        btn.classList.add('vf-btn-processing');
      }
    });

    // Icons and Text
    let icon = '🎙️';
    let text = 'Start Voice';
    let showEq = false;

    if (isListening) {
      icon = '⏹️';
      text = 'Stop & Fill';
      showEq = true;
    } else if (isSpeaking) {
      icon = '⏹️';
      text = 'Stop Speech';
      showEq = true;
    } else if (isProcessing) {
      icon = '⏳';
      text = 'Thinking...';
    } else if (isFilling) {
      icon = '⚡';
      text = 'Filling...';
    }

    if (this.bottomVoiceIcon) this.bottomVoiceIcon.textContent = icon;
    if (this.bottomVoiceText) this.bottomVoiceText.textContent = text;
    if (this.headerVoiceIcon) this.headerVoiceIcon.textContent = icon;
    if (this.headerVoiceText) this.headerVoiceText.textContent = text;

    const bottomEq = this.shadow?.getElementById('vf-bottom-voice-eq');
    const headerEq = this.shadow?.getElementById('vf-header-voice-eq');
    if (bottomEq) bottomEq.style.display = showEq ? 'inline-flex' : 'none';
    if (headerEq) headerEq.style.display = showEq ? 'inline-flex' : 'none';

    // Toggle cancel button visibility (only visible during listening)
    if (this.bottomCancelBtn) {
      this.bottomCancelBtn.style.display = isListening ? 'inline-flex' : 'none';
    }
    if (this.headerCancelBtn) {
      this.headerCancelBtn.style.display = isListening ? 'inline-flex' : 'none';
    }

    if (!isListening && this.bottomLiveChipEl) {
      this.bottomLiveChipEl.style.display = 'none';
    }

    // Update Meta State Pill
    if (this.metaStateEl) {
      let stateColor = '#94a3b8';
      if (isSpeaking) stateColor = '#c084fc';
      else if (this.voiceStatus === 'interrupted') stateColor = '#f43f5e';
      else if (isListening) stateColor = '#f87171';
      else if (isProcessing) stateColor = '#facc15';
      else if (isFilling) stateColor = '#4ade80';

      this.metaStateEl.style.color = stateColor;
      this.metaStateEl.innerHTML = `
        <span class="vf-live-dot" style="background: ${stateColor}"></span>
        <span>${this.voiceStatus.toUpperCase()}</span>
      `;
    }

    if (this.metaGenEl) {
      this.metaGenEl.textContent = `Gen #${this.currentGenerationId}`;
    }
  }

  private syncWsStatusUI(): void {
    if (!this.metaWsEl) return;
    const isConn = this.wsStatus === 'CONNECTED';
    const isConnecting = this.wsStatus === 'CONNECTING';
    const color = isConn ? '#4ade80' : (isConnecting ? '#facc15' : '#94a3b8');
    this.metaWsEl.style.color = color;
    this.metaWsEl.innerHTML = `
      <span class="vf-live-dot" style="background: ${color}"></span>
      <span>${this.wsStatus}</span>
      ${this.wsSessionId ? `<span style="color:#64748b; font-size:10px;">(${this.wsSessionId.slice(0, 8)})</span>` : ''}
    `;
  }

  private syncAiPanelUI(): void {
    if (!this.aiPanelEl) return;
    const hasData = this.latestTranscript || this.extractedActions.length > 0 || this.fillResults.length > 0 || this.askUserQuestion || this.aiErrorMessage || this.assistantResponseText;
    if (!hasData && this.voiceStatus === 'idle') {
      this.aiPanelEl.innerHTML = '';
      return;
    }

    let html = `<div class="vf-ai-panel">`;

    if (this.latestTranscript) {
      html += `
        <div class="vf-transcript-box">
          <div style="font-weight:600; color:#38bdf8; margin-bottom:2px;">🎙️ You Said:</div>
          <div>"${escapeHtml(this.latestTranscript)}"</div>
        </div>`;
    }

    if (this.assistantResponseText) {
      html += `
        <div class="vf-response-box">
          <div style="font-weight:600; color:#c084fc; margin-bottom:2px;">🔊 Assistant:</div>
          <div>"${escapeHtml(this.assistantResponseText)}"</div>
        </div>`;
    }

    if (this.extractedActions.length > 0) {
      html += `
        <div style="margin-top:6px; margin-bottom:6px;">
          <div style="font-size:11px; font-weight:600; color:#94a3b8; margin-bottom:4px;">Filled Actions:</div>
          <div>
            ${this.extractedActions.map(a => `<span class="vf-action-badge">⚡ ${escapeHtml(a.field_id)} = "${escapeHtml(String(a.value))}"</span>`).join('')}
          </div>
        </div>`;
    }

    if (this.askUserQuestion) {
      html += `
        <div style="background: rgba(245, 158, 11, 0.15); border-left: 3px solid #f59e0b; padding: 6px 10px; border-radius: 4px; margin-top: 6px; font-size: 12px; color: #fde68a;">
          ❓ <strong>Clarification:</strong> ${escapeHtml(this.askUserQuestion)}
        </div>`;
    }

    if (this.aiErrorMessage) {
      html += `
        <div style="background: rgba(239, 68, 68, 0.15); border-left: 3px solid #ef4444; padding: 6px 10px; border-radius: 4px; margin-top: 6px; font-size: 12px; color: #fca5a5;">
          ⚠️ ${escapeHtml(this.aiErrorMessage)}
        </div>`;
    }

    html += `</div>`;
    this.aiPanelEl.innerHTML = html;
  }

  public updateScanResult(result: PageScanResult, latencyMs?: number): void {
    this.currentResult = result;
    if (latencyMs !== undefined) {
      this.lastLatencyMs = latencyMs;
    }

    const totalFields = result.totalFieldCount;
    if (this.bottomPillEl) {
      this.bottomPillEl.textContent = `${totalFields} fields`;
    }

    if (this.metaCountEl) {
      const formsCount = result.forms.length;
      const orphanCount = result.orphanFields.length;
      const latencyStr = this.lastLatencyMs !== null ? ` • DOM: ${this.lastLatencyMs}ms` : '';
      const interruptStr = this.lastInterruptionLatencyMs !== null ? ` • Interrupt: ${this.lastInterruptionLatencyMs.toFixed(1)}ms (x${this.interruptionCount})` : '';
      this.metaCountEl.innerHTML = `
        <span>Detected: <strong>${formsCount}</strong> form(s), <strong>${orphanCount}</strong> orphan(s)</span>
        <span style="color:#94a3b8;">${latencyStr}</span>
        <span style="color:#f43f5e; font-weight:700;">${interruptStr}</span>
      `;
    }

    if (this.formsListEl) {
      let html = '';
      if (result.forms.length === 0 && result.orphanFields.length === 0) {
        html = `<div style="text-align: center; padding: 36px 16px; color: #64748b;">No form fields detected.</div>`;
      } else {
        result.forms.forEach((form, idx) => {
          html += `
            <div class="vf-section">
              <div class="vf-section-header">
                <span>📋 Form #${idx + 1} (${escapeHtml(form.title || form.name || form.formId || 'unnamed')})</span>
                <span class="vf-pill-badge">${form.fields.length} fields</span>
              </div>
              <div>${form.fields.map(f => this.renderFieldCard(f)).join('')}</div>
            </div>`;
        });
        if (result.orphanFields.length > 0) {
          html += `
            <div class="vf-section">
              <div class="vf-section-header">
                <span>🌐 Orphan Fields</span>
                <span class="vf-pill-badge">${result.orphanFields.length} fields</span>
              </div>
              <div>${result.orphanFields.map(f => this.renderFieldCard(f)).join('')}</div>
            </div>`;
        }
      }
      this.formsListEl.innerHTML = html;
      this.bindFieldCardHovers();
    }
  }

  private renderFieldCard(field: FormField): string {
    const valStr = typeof field.currentValue === 'boolean'
      ? (field.currentValue ? 'Checked' : 'Unchecked')
      : (field.currentValue ? `"${escapeHtml(String(field.currentValue))}"` : '<empty>');

    return `
      <div class="vf-field-card" data-selector="${escapeHtml(field.selector)}">
        <div class="vf-field-top">
          <span class="vf-field-label">${escapeHtml(field.label)}</span>
          <div>
            <span class="vf-tag vf-tag-type">${field.type}</span>
            ${field.validation.required ? '<span class="vf-tag vf-tag-req">REQ</span>' : ''}
          </div>
        </div>
        <div class="vf-field-detail" style="color: #64748b; font-family: monospace;">${escapeHtml(field.selector)}</div>
        <div class="vf-field-detail">Value: <span class="vf-field-val">${valStr}</span></div>
      </div>
    `;
  }

  private bindFieldCardHovers(): void {
    if (!this.shadow) return;
    const cards = this.shadow.querySelectorAll<HTMLElement>('.vf-field-card');
    cards.forEach(card => {
      card.addEventListener('mouseenter', () => {
        const selector = card.getAttribute('data-selector');
        if (selector) {
          try {
            const target = document.querySelector<HTMLElement>(selector);
            if (target) this.highlightElement(target);
          } catch {}
        }
      });
      card.addEventListener('mouseleave', () => this.clearHighlight());
    });
  }

  private highlightElement(element: HTMLElement): void {
    this.clearHighlight();
    this.highlightedElement = element;
    element.setAttribute('data-vf-highlight', 'true');
    element.style.outline = '2px solid #38bdf8';
    element.style.outlineOffset = '2px';
    element.style.boxShadow = '0 0 12px rgba(56, 189, 248, 0.4)';
    element.style.transition = 'all 0.2s ease';
  }

  private clearHighlight(): void {
    if (this.highlightedElement) {
      this.highlightedElement.style.outline = '';
      this.highlightedElement.style.outlineOffset = '';
      this.highlightedElement.style.boxShadow = '';
      this.highlightedElement.removeAttribute('data-vf-highlight');
      this.highlightedElement = null;
    }
  }

  public updateWsStatus(status: string, sessionId?: string): void {
    this.wsStatus = status;
    if (sessionId) this.wsSessionId = sessionId;
    this.syncWsStatusUI();
  }

  public setVoiceState(status: 'idle' | 'listening' | 'processing' | 'filling' | 'speaking' | 'interrupted' | 'error'): void {
    this.voiceStatus = status;
    this.syncVoiceStateUI();
  }

  public getVoiceState(): string {
    return this.voiceStatus;
  }

  public getCurrentResult(): PageScanResult | null {
    return this.currentResult;
  }

  public getInterruptionCount(): number {
    return this.interruptionCount;
  }

  public setGenerationId(genId: number): void {
    this.currentGenerationId = genId;
    if (this.metaGenEl) {
      this.metaGenEl.textContent = `Gen #${genId}`;
    }
  }

  public recordInterruption(latencyMs: number): void {
    this.lastInterruptionLatencyMs = latencyMs;
    this.interruptionCount++;
    this.voiceStatus = 'interrupted';
    this.syncVoiceStateUI();
  }

  public setAssistantResponse(text: string): void {
    this.assistantResponseText = text;
    this.syncAiPanelUI();
  }

  public setTranscript(text: string): void {
    this.latestTranscript = text;
    if (this.bottomLiveChipEl && this.bottomLiveTextEl) {
      if (text.trim() && this.voiceStatus === 'listening') {
        this.bottomLiveChipEl.style.display = 'inline-flex';
        this.bottomLiveTextEl.textContent = text;
      } else {
        this.bottomLiveChipEl.style.display = 'none';
      }
    }
    this.syncAiPanelUI();
  }

  public setLiveTranscript(text: string): void {
    this.setTranscript(text);
  }

  public clearLiveTranscript(): void {
    if (this.bottomLiveChipEl) {
      this.bottomLiveChipEl.style.display = 'none';
    }
    if (this.bottomLiveTextEl) {
      this.bottomLiveTextEl.textContent = '';
    }
  }

  public setExtractedActions(actions: FormAction[]): void {
    this.extractedActions = actions;
    this.syncAiPanelUI();
  }

  public setFillResults(results: FillResult[]): void {
    this.fillResults = results;
    this.syncAiPanelUI();
  }

  public setAskUser(question: string): void {
    this.askUserQuestion = question;
    this.syncAiPanelUI();
  }

  public setAiError(error: string): void {
    this.aiErrorMessage = error;
    this.syncAiPanelUI();
  }
}

function escapeHtml(str?: string | null): string {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

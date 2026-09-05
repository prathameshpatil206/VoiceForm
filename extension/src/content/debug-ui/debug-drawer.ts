import { FormField, PageScanResult } from '../../types/schema';
import { FormAction, FillResult } from '../filler/types';

export class VoiceFormDebugDrawer {
  private host: HTMLElement | null = null;
  private shadow: ShadowRoot | null = null;
  private isOpen = false;
  private currentResult: PageScanResult | null = null;
  private lastLatencyMs: number | null = null;
  private onRescanRequested: () => void;
  private onFillRequested?: (action: FormAction) => FillResult;
  private onVoiceToggleRequested?: () => void;
  private highlightedElement: HTMLElement | null = null;
  private wsStatus: string = 'DISCONNECTED';
  private wsSessionId?: string;

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
  private onStopPlaybackRequested?: () => void;

  constructor(
    onRescanRequested: () => void,
    onFillRequested?: (action: FormAction) => FillResult,
    onVoiceToggleRequested?: () => void,
    onStopPlaybackRequested?: () => void
  ) {
    this.onRescanRequested = onRescanRequested;
    this.onFillRequested = onFillRequested;
    this.onVoiceToggleRequested = onVoiceToggleRequested;
    this.onStopPlaybackRequested = onStopPlaybackRequested;
    this.init();
  }

  private init(): void {
    if (document.querySelector('voiceform-debug-drawer')) return;

    this.host = document.createElement('voiceform-debug-drawer');
    this.shadow = this.host.attachShadow({ mode: 'open' });
    document.documentElement.appendChild(this.host);

    this.render();
  }

  public updateScanResult(result: PageScanResult, latencyMs?: number): void {
    this.currentResult = result;
    if (latencyMs !== undefined) {
      this.lastLatencyMs = latencyMs;
    }
    this.render();
  }

  public updateWsStatus(status: string, sessionId?: string): void {
    this.wsStatus = status;
    if (sessionId) {
      this.wsSessionId = sessionId;
    }
    this.render();
  }

  public setVoiceState(status: 'idle' | 'listening' | 'processing' | 'filling' | 'speaking' | 'interrupted' | 'error'): void {
    this.voiceStatus = status;
    this.render();
  }

  public setGenerationId(genId: number): void {
    this.currentGenerationId = genId;
    this.render();
  }

  public recordInterruption(latencyMs: number): void {
    this.lastInterruptionLatencyMs = latencyMs;
    this.interruptionCount++;
    this.voiceStatus = 'interrupted';
    this.render();
  }

  public setAssistantResponse(text: string): void {
    this.assistantResponseText = text;
    this.render();
  }

  public setTranscript(text: string): void {
    this.latestTranscript = text;
    this.render();
  }

  public setExtractedActions(actions: FormAction[]): void {
    this.extractedActions = actions;
    this.render();
  }

  public setFillResults(results: FillResult[]): void {
    this.fillResults = results;
    this.render();
  }

  public setAskUser(question: string): void {
    this.askUserQuestion = question;
    this.render();
  }

  public setAiError(error: string): void {
    this.aiErrorMessage = error;
    this.render();
  }

  public setVoiceToggleCallback(cb: () => void): void {
    this.onVoiceToggleRequested = cb;
  }

  public setStopPlaybackCallback(cb: () => void): void {
    this.onStopPlaybackRequested = cb;
  }

  private render(): void {
    if (!this.shadow) return;

    const totalFields = this.currentResult?.totalFieldCount ?? 0;
    const formsCount = this.currentResult?.forms.length ?? 0;
    const orphanCount = this.currentResult?.orphanFields.length ?? 0;

    const isListening = this.voiceStatus === 'listening';
    const isProcessing = this.voiceStatus === 'processing';
    const isSpeaking = this.voiceStatus === 'speaking';
    const isFilling = this.voiceStatus === 'filling';

    let badgeBorderClass = '';
    if (isListening) badgeBorderClass = 'vf-pulse-listening';
    else if (isProcessing) badgeBorderClass = 'vf-pulse-processing';
    else if (isSpeaking) badgeBorderClass = 'vf-pulse-speaking';
    else if (isFilling) badgeBorderClass = 'vf-pulse-filling';

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
          bottom: 18px;
          right: 18px;
        }

        * {
          box-sizing: border-box;
        }

        /* Keyframe Animations */
        @keyframes pulseGlow {
          0%, 100% {
            box-shadow: 0 0 15px rgba(56, 189, 248, 0.4), 0 4px 20px rgba(0, 0, 0, 0.4);
            border-color: rgba(56, 189, 248, 0.6);
          }
          50% {
            box-shadow: 0 0 25px rgba(56, 189, 248, 0.8), 0 4px 25px rgba(0, 0, 0, 0.6);
            border-color: rgba(14, 165, 233, 1);
          }
        }

        @keyframes pulseRed {
          0%, 100% {
            box-shadow: 0 0 16px rgba(239, 68, 68, 0.5), 0 4px 20px rgba(0, 0, 0, 0.5);
            border-color: rgba(239, 68, 68, 0.8);
          }
          50% {
            box-shadow: 0 0 30px rgba(239, 68, 68, 0.9), 0 4px 30px rgba(0, 0, 0, 0.7);
            border-color: rgba(248, 113, 113, 1);
          }
        }

        @keyframes pulsePurple {
          0%, 100% {
            box-shadow: 0 0 16px rgba(168, 85, 247, 0.5), 0 4px 20px rgba(0, 0, 0, 0.5);
            border-color: rgba(168, 85, 247, 0.8);
          }
          50% {
            box-shadow: 0 0 30px rgba(192, 132, 252, 0.9), 0 4px 30px rgba(0, 0, 0, 0.7);
            border-color: rgba(216, 180, 254, 1);
          }
        }

        @keyframes shimmerGradient {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }

        @keyframes waveBar {
          0%, 100% { transform: scaleY(0.3); }
          50% { transform: scaleY(1.0); }
        }

        @keyframes spinRing {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }

        @keyframes slideInUp {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes liveDotPing {
          0% { transform: scale(1); opacity: 1; }
          75%, 100% { transform: scale(2.2); opacity: 0; }
        }

        /* Floating Badge */
        .vf-badge {
          display: flex;
          align-items: center;
          gap: 9px;
          background: rgba(15, 23, 42, 0.88);
          backdrop-filter: blur(14px);
          -webkit-backdrop-filter: blur(14px);
          color: #f8fafc;
          padding: 8px 16px;
          border-radius: 9999px;
          border: 1px solid rgba(255, 255, 255, 0.12);
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
          cursor: pointer;
          font-weight: 600;
          font-size: 13px;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
          user-select: none;
          position: relative;
        }

        .vf-badge:hover {
          transform: translateY(-2px) scale(1.02);
          background: rgba(30, 41, 59, 0.95);
          border-color: rgba(56, 189, 248, 0.4);
          box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55), 0 0 15px rgba(56, 189, 248, 0.25);
        }

        .vf-pulse-listening {
          animation: pulseRed 1.4s infinite ease-in-out;
          border-color: #ef4444 !important;
        }

        .vf-pulse-processing {
          animation: pulseGlow 1.2s infinite ease-in-out;
          border-color: #38bdf8 !important;
        }

        .vf-pulse-speaking {
          animation: pulsePurple 1.4s infinite ease-in-out;
          border-color: #a855f7 !important;
        }

        .vf-pulse-filling {
          box-shadow: 0 0 20px rgba(16, 185, 129, 0.6) !important;
          border-color: #10b981 !important;
        }

        /* Soundwave Equalizer */
        .vf-eq {
          display: flex;
          align-items: center;
          gap: 2.5px;
          height: 14px;
        }

        .vf-eq-bar {
          width: 3px;
          height: 14px;
          border-radius: 9999px;
          background: #38bdf8;
          transform-origin: bottom;
        }

        .vf-eq-active .vf-eq-bar {
          animation: waveBar 0.8s infinite ease-in-out;
        }

        .vf-eq-bar:nth-child(1) { animation-delay: 0.0s; height: 10px; }
        .vf-eq-bar:nth-child(2) { animation-delay: 0.2s; height: 14px; }
        .vf-eq-bar:nth-child(3) { animation-delay: 0.4s; height: 12px; }
        .vf-eq-bar:nth-child(4) { animation-delay: 0.1s; height: 8px; }

        .vf-pill {
          background: rgba(3, 105, 161, 0.8);
          color: #e0f2fe;
          padding: 2px 8px;
          border-radius: 9999px;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.02em;
          border: 1px solid rgba(56, 189, 248, 0.2);
        }

        /* Drawer Overlay */
        .vf-drawer {
          position: fixed;
          top: 0;
          right: 0;
          bottom: 0;
          width: 460px;
          max-width: 92vw;
          background: rgba(10, 15, 29, 0.94);
          backdrop-filter: blur(24px);
          -webkit-backdrop-filter: blur(24px);
          border-left: 1px solid rgba(56, 189, 248, 0.18);
          box-shadow: -12px 0 40px rgba(0, 0, 0, 0.6);
          display: flex;
          flex-direction: column;
          transform: translateX(${this.isOpen ? '0' : '100%'});
          transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
        }

        /* Header */
        .vf-header {
          padding: 16px 18px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(15, 23, 42, 0.95);
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
          letter-spacing: -0.01em;
        }

        .vf-header-actions {
          display: flex;
          gap: 8px;
        }

        .vf-btn {
          background: rgba(30, 41, 59, 0.9);
          color: #cbd5e1;
          border: 1px solid rgba(255, 255, 255, 0.1);
          padding: 6px 12px;
          border-radius: 7px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .vf-btn:hover {
          background: rgba(51, 65, 85, 0.95);
          color: #ffffff;
          transform: translateY(-1px);
        }

        .vf-btn:active {
          transform: translateY(0) scale(0.97);
        }

        .vf-btn-primary {
          background: linear-gradient(135deg, #0284c7, #0369a1);
          border-color: rgba(56, 189, 248, 0.4);
          color: #ffffff;
          box-shadow: 0 2px 8px rgba(2, 132, 199, 0.35);
        }

        .vf-btn-primary:hover {
          background: linear-gradient(135deg, #0369a1, #0284c7);
          box-shadow: 0 4px 12px rgba(2, 132, 199, 0.5);
        }

        /* Meta Bar */
        .vf-meta {
          padding: 10px 18px;
          background: rgba(11, 17, 32, 0.85);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 11px;
          color: #94a3b8;
        }

        .vf-latency {
          color: #10b981;
          font-weight: 600;
        }

        /* Content List */
        .vf-body {
          flex: 1;
          overflow-y: auto;
          padding: 18px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .vf-section {
          background: rgba(15, 23, 42, 0.75);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          overflow: hidden;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
          animation: slideInUp 0.22s ease-out;
        }

        .vf-section-header {
          padding: 11px 16px;
          background: rgba(30, 41, 59, 0.8);
          font-weight: 600;
          font-size: 13px;
          color: #f1f5f9;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .vf-field-card {
          padding: 12px 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          transition: all 0.15s ease;
          cursor: pointer;
        }

        .vf-field-card:last-child {
          border-bottom: none;
        }

        .vf-field-card:hover {
          background: rgba(23, 37, 84, 0.5);
          border-left: 2px solid #38bdf8;
          padding-left: 14px;
        }

        .vf-field-top {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          margin-bottom: 4px;
        }

        .vf-field-label {
          font-weight: 600;
          color: #38bdf8;
          font-size: 13px;
        }

        .vf-tag {
          font-size: 10px;
          font-weight: 700;
          padding: 2px 7px;
          border-radius: 4px;
          text-transform: uppercase;
        }

        .vf-tag-type {
          background: rgba(51, 65, 85, 0.8);
          color: #cbd5e1;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .vf-tag-req {
          background: rgba(127, 29, 29, 0.8);
          color: #fecaca;
          border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .vf-field-detail {
          font-size: 11px;
          color: #94a3b8;
          margin-top: 2px;
          word-break: break-all;
        }

        .vf-field-selector {
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          color: #a5b4fc;
          font-size: 10.5px;
        }

        .vf-field-val {
          color: #34d399;
          font-weight: 600;
        }

        .vf-options-list {
          margin-top: 6px;
          padding-left: 10px;
          border-left: 2px solid rgba(56, 189, 248, 0.3);
          font-size: 11px;
          color: #cbd5e1;
        }

        .vf-empty-msg {
          text-align: center;
          padding: 36px 16px;
          color: #64748b;
        }

        /* Pulsing Dot */
        .vf-live-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          display: inline-block;
          position: relative;
        }

        .vf-live-dot::after {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; bottom: 0;
          border-radius: 50%;
          background: inherit;
          animation: liveDotPing 1.6s cubic-bezier(0, 0, 0.2, 1) infinite;
        }

        /* Spinner */
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

      <!-- Trigger Badge -->
      <div class="vf-badge ${badgeBorderClass}" id="vf-toggle-btn">
        <span style="font-size: 16px; color: ${isListening ? '#f87171' : (isSpeaking ? '#c084fc' : '#38bdf8')}">⚡</span>
        <span>VoiceForm</span>
        
        ${isListening ? `
          <div class="vf-eq vf-eq-active">
            <span class="vf-eq-bar" style="background:#ef4444"></span>
            <span class="vf-eq-bar" style="background:#ef4444"></span>
            <span class="vf-eq-bar" style="background:#ef4444"></span>
            <span class="vf-eq-bar" style="background:#ef4444"></span>
          </div>
        ` : (isSpeaking ? `
          <div class="vf-eq vf-eq-active">
            <span class="vf-eq-bar" style="background:#a855f7"></span>
            <span class="vf-eq-bar" style="background:#a855f7"></span>
            <span class="vf-eq-bar" style="background:#a855f7"></span>
            <span class="vf-eq-bar" style="background:#a855f7"></span>
          </div>
        ` : (isProcessing ? `
          <span class="vf-spinner"></span>
        ` : ''))}

        <span class="vf-pill">${totalFields} fields</span>
      </div>

      <!-- Sliding Drawer -->
      <div class="vf-drawer">
        <div class="vf-header">
          <div class="vf-title">
            <span style="color:#38bdf8">⚡</span> VoiceForm Inspector
          </div>
          <div class="vf-header-actions">
            <button class="vf-btn" id="vf-voice-btn" style="background:${isSpeaking ? '#8b5cf6' : (isListening ? '#ef4444' : (isProcessing ? '#f59e0b' : (isFilling ? '#10b981' : '#0284c7')))};color:#fff;border-color:transparent;font-weight:600;">
              ${isSpeaking ? '⏹️ Stop Speech' : (isListening ? '⏹️ Stop Voice' : (isProcessing ? '⏳ Reasoning...' : (isFilling ? '⚡ Filling...' : '🎙️ Start Voice')))}
            </button>
            <button class="vf-btn" id="vf-fill-btn" style="background: rgba(15, 118, 110, 0.9); color:#fff; border-color: rgba(20, 184, 166, 0.4);">⚡ Fill Demo</button>
            <button class="vf-btn" id="vf-copy-btn">Copy JSON</button>
            <button class="vf-btn vf-btn-primary" id="vf-rescan-btn">Scan</button>
            <button class="vf-btn" id="vf-close-btn" style="padding: 6px 10px;">✕</button>
          </div>
        </div>

        <div class="vf-meta">
          <div>
            <span>Detected: <strong>${formsCount}</strong> form(s), <strong>${orphanCount}</strong> orphan(s)</span>
            ${this.lastLatencyMs !== null ? `<span class="vf-latency"> • DOM: ${this.lastLatencyMs}ms</span>` : ''}
            ${this.lastInterruptionLatencyMs !== null ? `<span style="color:#f43f5e; font-weight:700;"> • Interrupt: ${this.lastInterruptionLatencyMs.toFixed(1)}ms</span>` : ''}
          </div>
          <div style="display:flex; gap:12px; align-items:center;">
            <span style="font-weight:700; color: #38bdf8;">
              Gen #${this.currentGenerationId}
            </span>
            <span style="display:inline-flex; align-items:center; gap:5px; font-weight:600; color: ${isSpeaking ? '#c084fc' : (this.voiceStatus === 'interrupted' ? '#f43f5e' : (isListening ? '#f87171' : (isProcessing ? '#facc15' : (isFilling ? '#4ade80' : '#94a3b8'))))}">
              <span class="vf-live-dot" style="background: ${isSpeaking ? '#c084fc' : (isListening ? '#f87171' : (isProcessing ? '#facc15' : (isFilling ? '#4ade80' : '#94a3b8')))}"></span>
              ${this.voiceStatus.toUpperCase()}
            </span>
            <span style="display:inline-flex; align-items:center; gap:5px; font-weight:600; color: ${this.wsStatus === 'CONNECTED' ? '#4ade80' : (this.wsStatus === 'CONNECTING' ? '#facc15' : '#94a3b8')}">
              <span class="vf-live-dot" style="background: ${this.wsStatus === 'CONNECTED' ? '#4ade80' : (this.wsStatus === 'CONNECTING' ? '#facc15' : '#94a3b8')}"></span>
              ${this.wsStatus}
            </span>
            ${this.wsSessionId ? `<span style="color:#64748b; font-size:10px;">(${this.wsSessionId.slice(0, 8)})</span>` : ''}
          </div>
        </div>

        <div class="vf-body">
          ${this.renderAiPanel()}
          ${this.renderFormsList()}
        </div>
      </div>
    `;

    this.bindEvents();
  }

  private renderAiPanel(): string {
    const hasData = this.latestTranscript || this.extractedActions.length > 0 || this.fillResults.length > 0 || this.askUserQuestion || this.aiErrorMessage || this.assistantResponseText || this.lastInterruptionLatencyMs !== null;
    if (!hasData && this.voiceStatus === 'idle') return '';

    let statusColor = '#94a3b8';
    let statusText = 'Idle';
    if (this.voiceStatus === 'listening') {
      statusColor = '#ef4444';
      statusText = '🎙️ Listening to microphone...';
    } else if (this.voiceStatus === 'interrupted') {
      statusColor = '#f43f5e';
      statusText = `⚡ Interrupted (${this.lastInterruptionLatencyMs !== null ? `${this.lastInterruptionLatencyMs.toFixed(1)}ms` : ''})`;
    } else if (this.voiceStatus === 'processing') {
      statusColor = '#f59e0b';
      statusText = '⏳ ASR & LLM Reasoning...';
    } else if (this.voiceStatus === 'filling') {
      statusColor = '#10b981';
      statusText = '⚡ Executing Form Fill...';
    } else if (this.voiceStatus === 'speaking') {
      statusColor = '#8b5cf6';
      statusText = '🔊 Speaking (Rime TTS)...';
    } else if (this.voiceStatus === 'error') {
      statusColor = '#f87171';
      statusText = '⚠️ Error encountered';
    }

    return `
      <div class="vf-section" style="border-color: rgba(56, 189, 248, 0.4); background: rgba(11, 19, 41, 0.9);">
        <div class="vf-section-header" style="background: rgba(30, 58, 138, 0.7); color: #bae6fd;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:14px;">🤖</span>
            <span>AI Voice Pipeline</span>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            ${this.voiceStatus === 'listening' || this.voiceStatus === 'speaking' ? `
              <div class="vf-eq vf-eq-active">
                <span class="vf-eq-bar" style="background:${this.voiceStatus === 'listening' ? '#ef4444' : '#c084fc'}"></span>
                <span class="vf-eq-bar" style="background:${this.voiceStatus === 'listening' ? '#ef4444' : '#c084fc'}"></span>
                <span class="vf-eq-bar" style="background:${this.voiceStatus === 'listening' ? '#ef4444' : '#c084fc'}"></span>
                <span class="vf-eq-bar" style="background:${this.voiceStatus === 'listening' ? '#ef4444' : '#c084fc'}"></span>
              </div>
            ` : (this.voiceStatus === 'processing' ? `<span class="vf-spinner"></span>` : '')}
            <span class="vf-pill" style="background:${statusColor}; color: #fff; border:none;">${statusText}</span>
          </div>
        </div>
        <div style="padding: 14px; display: flex; flex-direction: column; gap: 10px;">
          ${this.latestTranscript ? `
            <div style="animation: slideInUp 0.2s ease-out;">
              <div style="font-size: 11px; font-weight: 700; color: #94a3b8; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.03em;">🎙️ Transcript:</div>
              <div style="background: rgba(30, 41, 59, 0.85); padding: 9px 12px; border-radius: 7px; color: #f8fafc; font-style: italic; border: 1px solid rgba(255,255,255,0.06); box-shadow: inset 0 1px 3px rgba(0,0,0,0.3);">
                "${escapeHtml(this.latestTranscript)}"
              </div>
            </div>
          ` : ''}

          ${this.extractedActions.length > 0 ? `
            <div style="animation: slideInUp 0.2s ease-out;">
              <div style="font-size: 11px; font-weight: 700; color: #94a3b8; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.03em;">⚡ Extracted Actions (${this.extractedActions.length}):</div>
              <div style="display: flex; flex-direction: column; gap: 5px;">
                ${this.extractedActions.map(a => `
                  <div style="background: rgba(30, 41, 59, 0.85); padding: 7px 10px; border-radius: 6px; font-family: monospace; font-size: 12px; border: 1px solid rgba(56, 189, 248, 0.2); display:flex; justify-content:space-between; align-items:center;">
                    <span><span style="color: #38bdf8; font-weight:700;">${escapeHtml(a.action)}</span> ➜ <span style="color: #facc15;">${escapeHtml(a.field_id || a.selector || 'unknown')}</span></span>
                    <span style="color: #4ade80; font-weight:700;">"${escapeHtml(String(a.value))}"</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}

          ${this.assistantResponseText ? `
            <div style="background: rgba(6, 78, 59, 0.7); border: 1px solid rgba(5, 150, 105, 0.5); padding: 11px 14px; border-radius: 7px; color: #ecfdf5; animation: slideInUp 0.2s ease-out;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <span style="font-size: 11px; font-weight: 700; color: #6ee7b7; text-transform: uppercase;">🔊 Assistant Audio Confirmation:</span>
                ${this.voiceStatus === 'speaking' ? `
                  <button class="vf-btn" id="vf-stop-speech-btn" style="background: #ef4444; color: #fff; border-color: transparent; padding: 2px 8px; font-size: 11px; font-weight: 600;">⏹️ Stop Audio</button>
                ` : ''}
              </div>
              <div style="font-size: 13px; font-style: italic; line-height: 1.45;">
                "${escapeHtml(this.assistantResponseText)}"
              </div>
            </div>
          ` : ''}

          ${this.askUserQuestion ? `
            <div style="background: rgba(69, 26, 3, 0.8); border: 1px solid rgba(180, 83, 9, 0.6); padding: 9px 12px; border-radius: 7px; color: #fef3c7; animation: slideInUp 0.2s ease-out;">
              <strong>❓ Clarification Needed:</strong> ${escapeHtml(this.askUserQuestion)}
            </div>
          ` : ''}

          ${this.aiErrorMessage ? `
            <div style="background: rgba(69, 10, 10, 0.85); border: 1px solid rgba(185, 28, 28, 0.6); padding: 9px 12px; border-radius: 7px; color: #fecaca; animation: slideInUp 0.2s ease-out;">
              <strong>⚠️ Error:</strong> ${escapeHtml(this.aiErrorMessage)}
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  private renderFormsList(): string {
    if (!this.currentResult || this.currentResult.totalFieldCount === 0) {
      return `<div class="vf-empty-msg">No form inputs detected on this page.</div>`;
    }

    let html = '';

    // 1. Detected Forms
    for (const form of this.currentResult.forms) {
      html += `
        <div class="vf-section">
          <div class="vf-section-header">
            <span>📋 ${escapeHtml(form.title || form.formId)}</span>
            <span class="vf-pill">${form.fieldCount} fields</span>
          </div>
          <div>
            ${form.fields.map(f => this.renderFieldCard(f)).join('')}
          </div>
        </div>
      `;
    }

    // 2. Orphan Fields
    if (this.currentResult.orphanFields.length > 0) {
      html += `
        <div class="vf-section">
          <div class="vf-section-header">
            <span>🌐 Orphan Fields (Outside &lt;form&gt;)</span>
            <span class="vf-pill">${this.currentResult.orphanFields.length} fields</span>
          </div>
          <div>
            ${this.currentResult.orphanFields.map(f => this.renderFieldCard(f)).join('')}
          </div>
        </div>
      `;
    }

    return html;
  }

  private renderFieldCard(field: FormField): string {
    const valStr = typeof field.currentValue === 'boolean'
      ? (field.currentValue ? 'Checked' : 'Unchecked')
      : (field.currentValue ? `"${escapeHtml(field.currentValue)}"` : '<empty>');

    let optionsHtml = '';
    if (field.type === 'select' && field.options) {
      optionsHtml = `
        <div class="vf-options-list">
          Options (${field.options.length}): ${field.options.map(o => `${escapeHtml(o.label)} [${escapeHtml(o.value)}]${o.selected ? ' ✓' : ''}`).join(', ')}
        </div>
      `;
    } else if (field.type === 'radio' && field.radioOptions) {
      optionsHtml = `
        <div class="vf-options-list">
          Radio items (${field.radioOptions.length}): ${field.radioOptions.map(r => `${escapeHtml(r.label)} (${escapeHtml(r.value)})${r.checked ? ' ●' : ' ○'}`).join(' | ')}
        </div>
      `;
    }

    return `
      <div class="vf-field-card" data-selector="${escapeHtml(field.selector)}">
        <div class="vf-field-top">
          <span class="vf-field-label">${escapeHtml(field.label)}</span>
          <div>
            <span class="vf-tag vf-tag-type">${field.type}</span>
            ${field.validation.required ? '<span class="vf-tag vf-tag-req">REQ</span>' : ''}
          </div>
        </div>
        <div class="vf-field-detail vf-field-selector">${escapeHtml(field.selector)}</div>
        <div class="vf-field-detail">
          Value: <span class="vf-field-val">${valStr}</span>
          ${field.placeholder ? ` • Placeholder: "${escapeHtml(field.placeholder)}"` : ''}
          ${field.autocomplete ? ` • Autocomplete: ${escapeHtml(field.autocomplete)}` : ''}
        </div>
        ${optionsHtml}
      </div>
    `;
  }

  private bindEvents(): void {
    if (!this.shadow) return;

    // Toggle button
    const toggleBtn = this.shadow.getElementById('vf-toggle-btn');
    toggleBtn?.addEventListener('click', () => {
      this.isOpen = !this.isOpen;
      this.render();
    });

    // Voice / Stop Button
    const voiceBtn = this.shadow.getElementById('vf-voice-btn');
    voiceBtn?.addEventListener('click', () => {
      if (this.voiceStatus === 'speaking') {
        if (this.onStopPlaybackRequested) {
          this.onStopPlaybackRequested();
        }
      } else if (this.onVoiceToggleRequested) {
        this.onVoiceToggleRequested();
      }
    });

    // Dedicated Stop Speech Button in AI Panel
    const stopSpeechBtn = this.shadow.getElementById('vf-stop-speech-btn');
    stopSpeechBtn?.addEventListener('click', () => {
      if (this.onStopPlaybackRequested) {
        this.onStopPlaybackRequested();
      }
    });

    // Close button
    const closeBtn = this.shadow.getElementById('vf-close-btn');
    closeBtn?.addEventListener('click', () => {
      this.isOpen = false;
      this.render();
    });

    // Rescan button
    const rescanBtn = this.shadow.getElementById('vf-rescan-btn');
    rescanBtn?.addEventListener('click', () => {
      this.onRescanRequested();
    });

    // Copy JSON
    const copyBtn = this.shadow.getElementById('vf-copy-btn');
    copyBtn?.addEventListener('click', () => {
      if (this.currentResult) {
        navigator.clipboard.writeText(JSON.stringify(this.currentResult, null, 2))
          .then(() => {
            copyBtn.textContent = 'Copied!';
            setTimeout(() => { copyBtn.textContent = 'Copy JSON'; }, 1500);
          })
          .catch(() => alert('Failed to copy to clipboard'));
      }
    });

    // Fill Demo
    const fillBtn = this.shadow.getElementById('vf-fill-btn');
    fillBtn?.addEventListener('click', () => {
      if (!this.currentResult || !this.onFillRequested) return;
      const allFields = [
        ...this.currentResult.forms.flatMap(f => f.fields),
        ...this.currentResult.orphanFields
      ];
      for (const field of allFields) {
        if (field.disabled || field.readOnly) continue;
        let sampleVal: string | boolean = 'Alex Morgan';
        if (field.type === 'email') sampleVal = 'alex.morgan@example.com';
        else if (field.type === 'number') sampleVal = '30';
        else if (field.type === 'tel') sampleVal = '+1 (555) 234-5678';
        else if (field.type === 'date') sampleVal = '2026-09-05';
        else if (field.type === 'time') sampleVal = '14:30';
        else if (field.type === 'datetime-local') sampleVal = '2026-09-05T14:30';
        else if (field.type === 'checkbox') sampleVal = true;
        else if (field.type === 'select' && field.options && field.options.length > 1) {
          sampleVal = field.options[1].value;
        } else if (field.type === 'radio' && field.radioOptions && field.radioOptions.length > 1) {
          sampleVal = field.radioOptions[1].value;
        }

        this.onFillRequested({
          field_id: field.id,
          value: sampleVal
        });
      }
    });

    // Hover to highlight DOM element
    const cards = this.shadow.querySelectorAll<HTMLElement>('.vf-field-card');
    cards.forEach(card => {
      card.addEventListener('mouseenter', () => {
        const selector = card.getAttribute('data-selector');
        if (selector) {
          try {
            const target = document.querySelector<HTMLElement>(selector);
            if (target) {
              this.highlightElement(target);
            }
          } catch {
            // ignore invalid selector
          }
        }
      });
      card.addEventListener('mouseleave', () => {
        this.clearHighlight();
      });
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

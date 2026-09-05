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

  // Milestone 4, 5 & 6: Voice, AI, TTS & Interruption State
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

    this.shadow.innerHTML = `
      <style>
        :host {
          all: initial;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
          font-size: 13px;
          line-height: 1.4;
          color: #e2e8f0;
          z-index: 2147483647;
          position: fixed;
          bottom: 16px;
          right: 16px;
        }

        * {
          box-sizing: border-box;
        }

        /* Floating Badge */
        .vf-badge {
          display: flex;
          align-items: center;
          gap: 8px;
          background: #0f172a;
          color: #f8fafc;
          padding: 8px 14px;
          border-radius: 9999px;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.1);
          cursor: pointer;
          font-weight: 600;
          transition: transform 0.15s ease, background 0.15s ease;
          user-select: none;
        }

        .vf-badge:hover {
          transform: translateY(-2px);
          background: #1e293b;
        }

        .vf-badge-icon {
          color: #38bdf8;
          font-size: 15px;
        }

        .vf-pill {
          background: #0369a1;
          color: #e0f2fe;
          padding: 2px 8px;
          border-radius: 9999px;
          font-size: 11px;
          font-weight: 700;
        }

        /* Drawer Overlay */
        .vf-drawer {
          position: fixed;
          top: 0;
          right: 0;
          bottom: 0;
          width: 440px;
          max-width: 90vw;
          background: #090d16;
          border-left: 1px solid #1e293b;
          box-shadow: -10px 0 30px rgba(0, 0, 0, 0.5);
          display: flex;
          flex-direction: column;
          transform: translateX(${this.isOpen ? '0' : '100%'});
          transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }

        /* Header */
        .vf-header {
          padding: 16px;
          border-bottom: 1px solid #1e293b;
          background: #0f172a;
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
          gap: 6px;
        }

        .vf-header-actions {
          display: flex;
          gap: 8px;
        }

        .vf-btn {
          background: #1e293b;
          color: #cbd5e1;
          border: 1px solid #334155;
          padding: 5px 10px;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .vf-btn:hover {
          background: #334155;
          color: #ffffff;
        }

        .vf-btn-primary {
          background: #0284c7;
          border-color: #0369a1;
          color: #ffffff;
        }
        .vf-btn-primary:hover {
          background: #0369a1;
        }

        /* Meta Bar */
        .vf-meta {
          padding: 10px 16px;
          background: #0b1120;
          border-bottom: 1px solid #1e293b;
          display: flex;
          justify-content: space-between;
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
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .vf-section {
          background: #0f172a;
          border: 1px solid #1e293b;
          border-radius: 8px;
          overflow: hidden;
        }

        .vf-section-header {
          padding: 10px 14px;
          background: #1e293b;
          font-weight: 600;
          font-size: 13px;
          color: #f1f5f9;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .vf-field-card {
          padding: 12px 14px;
          border-bottom: 1px solid #1e293b;
          transition: background 0.15s ease;
          cursor: pointer;
        }

        .vf-field-card:last-child {
          border-bottom: none;
        }

        .vf-field-card:hover {
          background: #172554;
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
          font-weight: 600;
          padding: 2px 6px;
          border-radius: 4px;
          text-transform: uppercase;
        }

        .vf-tag-type {
          background: #334155;
          color: #cbd5e1;
        }

        .vf-tag-req {
          background: #7f1d1d;
          color: #fecaca;
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
          font-size: 10px;
        }

        .vf-field-val {
          color: #34d399;
          font-weight: 500;
        }

        .vf-options-list {
          margin-top: 6px;
          padding-left: 10px;
          border-left: 2px solid #334155;
          font-size: 11px;
          color: #cbd5e1;
        }

        .vf-empty-msg {
          text-align: center;
          padding: 32px 16px;
          color: #64748b;
        }
      </style>

      <!-- Trigger Badge -->
      <div class="vf-badge" id="vf-toggle-btn">
        <span class="vf-badge-icon">⚡</span>
        <span>VoiceForm</span>
        <span class="vf-pill">${totalFields} fields</span>
      </div>

      <!-- Sliding Drawer -->
      <div class="vf-drawer">
        <div class="vf-header">
          <div class="vf-title">
            <span style="color:#38bdf8">⚡</span> VoiceForm Inspector
          </div>
          <div class="vf-header-actions">
            <button class="vf-btn" id="vf-voice-btn" style="background:${this.voiceStatus === 'speaking' ? '#8b5cf6' : (this.voiceStatus === 'listening' ? '#ef4444' : (this.voiceStatus === 'processing' ? '#f59e0b' : (this.voiceStatus === 'filling' ? '#10b981' : '#0284c7')))};color:#fff;border-color:transparent;font-weight:600;">
              ${this.voiceStatus === 'speaking' ? '⏹️ Stop Speech' : (this.voiceStatus === 'listening' ? '⏹️ Stop Voice' : (this.voiceStatus === 'processing' ? '⏳ Processing...' : (this.voiceStatus === 'filling' ? '⚡ Filling...' : '🎙️ Start Voice')))}
            </button>
            <button class="vf-btn" id="vf-fill-btn" style="background:#0f766e;color:#fff;border-color:#115e59;">⚡ Fill Demo</button>
            <button class="vf-btn" id="vf-copy-btn">Copy JSON</button>
            <button class="vf-btn vf-btn-primary" id="vf-rescan-btn">Scan</button>
            <button class="vf-btn" id="vf-close-btn">✕</button>
          </div>
        </div>

        <div class="vf-meta">
          <div>
            <span>Detected: <strong>${formsCount}</strong> form(s), <strong>${orphanCount}</strong> orphan(s)</span>
            ${this.lastLatencyMs !== null ? `<span class="vf-latency"> • DOM: ${this.lastLatencyMs}ms</span>` : ''}
            ${this.lastInterruptionLatencyMs !== null ? `<span style="color:#f43f5e; font-weight:700;"> • Interrupt: ${this.lastInterruptionLatencyMs.toFixed(1)}ms</span>` : ''}
          </div>
          <div style="display:flex; gap:10px;">
            <span style="font-weight:700; color: #38bdf8;">
              Gen #${this.currentGenerationId}
            </span>
            <span style="font-weight:600; color: ${this.voiceStatus === 'speaking' ? '#c084fc' : (this.voiceStatus === 'interrupted' ? '#f43f5e' : (this.voiceStatus === 'listening' ? '#f87171' : (this.voiceStatus === 'processing' ? '#facc15' : (this.voiceStatus === 'filling' ? '#4ade80' : '#94a3b8'))))}">
              ● State: ${this.voiceStatus.toUpperCase()}
            </span>
            <span style="font-weight:600; color: ${this.wsStatus === 'CONNECTED' ? '#4ade80' : (this.wsStatus === 'CONNECTING' ? '#facc15' : '#94a3b8')}">
              ● WS: ${this.wsStatus}
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
      statusText = '⏳ ASR & LLM Processing...';
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
      <div class="vf-section" style="border-color: #0284c7; background: #0b1329;">
        <div class="vf-section-header" style="background: #1e3a8a; color: #bae6fd;">
          <span>🤖 AI Voice Pipeline</span>
          <span class="vf-pill" style="background:${statusColor}; color: #fff;">${statusText}</span>
        </div>
        <div style="padding: 12px; display: flex; flex-direction: column; gap: 8px;">
          ${this.latestTranscript ? `
            <div>
              <div style="font-size: 11px; font-weight: 600; color: #94a3b8; margin-bottom: 2px;">LATEST TRANSCRIPT:</div>
              <div style="background: #1e293b; padding: 8px 10px; border-radius: 6px; color: #f8fafc; font-style: italic;">
                "${escapeHtml(this.latestTranscript)}"
              </div>
            </div>
          ` : ''}

          ${this.extractedActions.length > 0 ? `
            <div>
              <div style="font-size: 11px; font-weight: 600; color: #94a3b8; margin-bottom: 2px;">EXTRACTED ACTIONS (${this.extractedActions.length}):</div>
              <div style="display: flex; flex-direction: column; gap: 4px;">
                ${this.extractedActions.map(a => `
                  <div style="background: #1e293b; padding: 6px 8px; border-radius: 4px; font-family: monospace; font-size: 12px;">
                    <span style="color: #38bdf8;">${escapeHtml(a.action)}</span> ➜ <span style="color: #facc15;">${escapeHtml(a.field_id || a.selector || 'unknown')}</span> = <span style="color: #4ade80;">"${escapeHtml(String(a.value))}"</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}

          ${this.assistantResponseText ? `
            <div style="background: #064e3b; border: 1px solid #059669; padding: 10px 12px; border-radius: 6px; color: #ecfdf5;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 11px; font-weight: 700; color: #6ee7b7; text-transform: uppercase;">🔊 Assistant Response (Rime TTS):</span>
                ${this.voiceStatus === 'speaking' ? `
                  <button class="vf-btn" id="vf-stop-speech-btn" style="background: #ef4444; color: #fff; border-color: transparent; padding: 2px 8px; font-size: 11px; font-weight: 600;">⏹️ Stop Audio</button>
                ` : ''}
              </div>
              <div style="font-size: 13px; font-style: italic; line-height: 1.4;">
                "${escapeHtml(this.assistantResponseText)}"
              </div>
            </div>
          ` : ''}

          ${this.askUserQuestion ? `
            <div style="background: #451a03; border: 1px solid #b45309; padding: 8px 10px; border-radius: 6px; color: #fef3c7;">
              <strong>❓ Assistant Question:</strong> ${escapeHtml(this.askUserQuestion)}
            </div>
          ` : ''}

          ${this.aiErrorMessage ? `
            <div style="background: #450a0a; border: 1px solid #b91c1c; padding: 8px 10px; border-radius: 6px; color: #fecaca;">
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
        let sampleVal: string | boolean = 'Jane Doe';
        if (field.type === 'email') sampleVal = 'jane.doe@example.com';
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
  }

  private clearHighlight(): void {
    if (this.highlightedElement) {
      this.highlightedElement.style.outline = '';
      this.highlightedElement.style.outlineOffset = '';
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

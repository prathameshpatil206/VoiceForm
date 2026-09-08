import { PageScanResult } from '../../types/schema';
import { FillResult, FormAction } from '../filler/types';

export type ConnectionStatus = 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'RECONNECTING';

export interface WSMessage<T = any> {
  version: number;
  type: string;
  session_id: string;
  generation_id?: number;
  timestamp: number;
  payload: T;
}

export interface WSClientOptions {
  url?: string;
  autoConnect?: boolean;
  onStatusChange?: (status: ConnectionStatus) => void;
  onConnected?: (sessionId: string) => void;
  onFillActionReceived?: (action: FormAction, generationId?: number) => FillResult;
  onFillActionsReceived?: (actions: FormAction[], generationId?: number) => FillResult[];
  onTranscriptReceived?: (transcript: string, language?: string, generationId?: number) => void;
  onAiActionsReceived?: (actions: FormAction[], generationId?: number) => void;
  onAiResponseReceived?: (response: string, generationId?: number) => void;
  onAskUserReceived?: (question: string, generationId?: number) => void;
  onAiErrorReceived?: (error: { code: string; message: string; stage?: string; generation_id?: number }) => void;
  onTtsStart?: (payload: { request_id: string; text: string; format: string; sample_rate: number; generation_id?: number }) => void;
  onTtsAudio?: (payload: { request_id: string; chunk_index: number; audio_base64: string; format: string; is_final: boolean; generation_id?: number }) => void;
  onTtsEnd?: (payload: { request_id: string; total_chunks: number; generation_id?: number }) => void;
  onTtsError?: (payload: { request_id: string; error_code: string; message: string; details?: string; generation_id?: number }) => void;
  onTtsCancel?: (payload: { request_id: string; generation_id?: number }) => void;
  onGenerationStart?: (payload: { generation_id: number; trigger: string }) => void;
  onGenerationCancelled?: (payload: { generation_id: number; reason: string }) => void;
  onGenerationComplete?: (payload: { generation_id: number; status: string }) => void;
}

export class VoiceFormWebSocketClient {
  private socket: WebSocket | null = null;
  private port: chrome.runtime.Port | null = null;
  private url: string;
  private sessionId: string;
  private activeGenerationId = 0;
  private status: ConnectionStatus = 'DISCONNECTED';
  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;
  private reconnectDelayMs = 1000;
  private maxReconnectDelayMs = 8000;
  private intentionallyClosed = false;

  private onStatusChangeCallback?: (status: ConnectionStatus) => void;
  private onConnectedCallback?: (sessionId: string) => void;
  private onFillActionReceivedCallback?: (action: FormAction, generationId?: number) => FillResult;
  private onFillActionsReceivedCallback?: (actions: FormAction[], generationId?: number) => FillResult[];
  private onTranscriptReceivedCallback?: (transcript: string, language?: string, generationId?: number) => void;
  private onAiActionsReceivedCallback?: (actions: FormAction[], generationId?: number) => void;
  private onAiResponseReceivedCallback?: (response: string, generationId?: number) => void;
  private onAskUserReceivedCallback?: (question: string, generationId?: number) => void;
  private onAiErrorReceivedCallback?: (error: { code: string; message: string; stage?: string; generation_id?: number }) => void;
  private onTtsStartCallback?: (payload: { request_id: string; text: string; format: string; sample_rate: number; generation_id?: number }) => void;
  private onTtsAudioCallback?: (payload: { request_id: string; chunk_index: number; audio_base64: string; format: string; is_final: boolean; generation_id?: number }) => void;
  private onTtsEndCallback?: (payload: { request_id: string; total_chunks: number; generation_id?: number }) => void;
  private onTtsErrorCallback?: (payload: { request_id: string; error_code: string; message: string; details?: string; generation_id?: number }) => void;
  private onTtsCancelCallback?: (payload: { request_id: string; generation_id?: number }) => void;
  private onGenerationStartCallback?: (payload: { generation_id: number; trigger: string }) => void;
  private onGenerationCancelledCallback?: (payload: { generation_id: number; reason: string }) => void;
  private onGenerationCompleteCallback?: (payload: { generation_id: number; status: string }) => void;

  constructor(options: WSClientOptions = {}) {
    this.url = options.url || 'ws://127.0.0.1:8765/ws';
    this.sessionId = `sess_${Math.random().toString(36).substring(2, 10)}`;
    this.onStatusChangeCallback = options.onStatusChange;
    this.onConnectedCallback = options.onConnected;
    this.onFillActionReceivedCallback = options.onFillActionReceived;
    this.onFillActionsReceivedCallback = options.onFillActionsReceived;
    this.onTranscriptReceivedCallback = options.onTranscriptReceived;
    this.onAiActionsReceivedCallback = options.onAiActionsReceived;
    this.onAiResponseReceivedCallback = options.onAiResponseReceived;
    this.onAskUserReceivedCallback = options.onAskUserReceived;
    this.onAiErrorReceivedCallback = options.onAiErrorReceived;
    this.onTtsStartCallback = options.onTtsStart;
    this.onTtsAudioCallback = options.onTtsAudio;
    this.onTtsEndCallback = options.onTtsEnd;
    this.onTtsErrorCallback = options.onTtsError;
    this.onTtsCancelCallback = options.onTtsCancel;
    this.onGenerationStartCallback = options.onGenerationStart;
    this.onGenerationCancelledCallback = options.onGenerationCancelled;
    this.onGenerationCompleteCallback = options.onGenerationComplete;

    if (options.autoConnect) {
      this.connect();
    }
  }

  public getStatus(): ConnectionStatus {
    return this.status;
  }

  public getSessionId(): string {
    return this.sessionId;
  }

  public getActiveGenerationId(): number {
    return this.activeGenerationId;
  }

  public setActiveGenerationId(genId: number): void {
    if (genId > this.activeGenerationId) {
      this.activeGenerationId = genId;
    }
  }

  public setActionHandlers(
    onFill: (action: FormAction, generationId?: number) => FillResult,
    onFillBatch: (actions: FormAction[], generationId?: number) => FillResult[]
  ): void {
    this.onFillActionReceivedCallback = onFill;
    this.onFillActionsReceivedCallback = onFillBatch;
  }

  public setStatusCallback(cb: (status: ConnectionStatus) => void): void {
    this.onStatusChangeCallback = cb;
  }

  public connect(customSessionId?: string): void {
    if (customSessionId) {
      this.sessionId = customSessionId;
    }

    if (this.status === 'CONNECTED' || this.status === 'CONNECTING') {
      return;
    }

    this.intentionallyClosed = false;
    this.setStatus('CONNECTING');

    const fullUrl = `${this.url}/${this.sessionId}`;
    const isHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
    const hasChromeRuntime = typeof chrome !== 'undefined' && typeof chrome.runtime?.connect === 'function';

    // On HTTPS pages, direct ws:// is blocked by browser mixed content policy.
    // Use background service worker proxy port.
    if (hasChromeRuntime && isHttps) {
      this.connectViaBackgroundBridge(fullUrl);
      return;
    }

    // Direct WebSocket connection
    try {
      this.socket = new WebSocket(fullUrl);

      this.socket.onopen = () => {
        this.reconnectDelayMs = 1000;
        this.setStatus('CONNECTED');
        this.startHeartbeat();
        this.sendHello();
      };

      this.socket.onmessage = (event) => {
        this.handleMessage(event.data);
      };

      this.socket.onclose = (_event) => {
        this.stopHeartbeat();
        this.socket = null;
        if (!this.intentionallyClosed) {
          this.setStatus('RECONNECTING');
          this.scheduleReconnect();
        } else {
          this.setStatus('DISCONNECTED');
        }
      };

      this.socket.onerror = (err) => {
        console.warn('[VoiceForm WS] Socket direct connect error, attempting background bridge if available:', err);
        if (hasChromeRuntime && !this.port) {
          if (this.socket) {
            try { this.socket.close(); } catch {}
            this.socket = null;
          }
          this.connectViaBackgroundBridge(fullUrl);
        }
      };
    } catch (e) {
      console.warn('[VoiceForm WS] Direct WebSocket creation failed:', e);
      if (hasChromeRuntime) {
        this.connectViaBackgroundBridge(fullUrl);
      } else {
        this.scheduleReconnect();
      }
    }
  }

  private connectViaBackgroundBridge(fullUrl: string): void {
    try {
      this.port = chrome.runtime.connect({ name: 'voiceform-ws' });

      this.port.onMessage.addListener((msg: any) => {
        if (msg.type === '__WS_EVENT__') {
          if (msg.event === 'open') {
            this.reconnectDelayMs = 1000;
            this.setStatus('CONNECTED');
            this.startHeartbeat();
            this.sendHello();
          } else if (msg.event === 'message') {
            this.handleMessage(msg.data);
          } else if (msg.event === 'close') {
            this.stopHeartbeat();
            this.port = null;
            if (!this.intentionallyClosed) {
              this.setStatus('RECONNECTING');
              this.scheduleReconnect();
            } else {
              this.setStatus('DISCONNECTED');
            }
          } else if (msg.event === 'error') {
            console.warn('[VoiceForm WS Bridge] Bridge error:', msg.error);
          }
        }
      });

      this.port.onDisconnect.addListener(() => {
        this.port = null;
        this.stopHeartbeat();
        if (!this.intentionallyClosed) {
          this.setStatus('RECONNECTING');
          this.scheduleReconnect();
        } else {
          this.setStatus('DISCONNECTED');
        }
      });

      this.port.postMessage({ type: 'CONNECT', url: fullUrl });
    } catch (err) {
      console.error('[VoiceForm WS Bridge] Failed to connect port:', err);
      this.scheduleReconnect();
    }
  }

  public disconnect(): void {
    this.intentionallyClosed = true;
    this.stopHeartbeat();
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.port) {
      try {
        this.port.postMessage({ type: 'DISCONNECT' });
        this.port.disconnect();
      } catch {}
      this.port = null;
    }
    if (this.socket) {
      try {
        this.socket.close();
      } catch {}
      this.socket = null;
    }
    this.setStatus('DISCONNECTED');
  }

  public send<T = any>(type: string, payload: T, generationId?: number): boolean {
    const isSocketOpen = this.socket && this.socket.readyState === WebSocket.OPEN;
    const isPortOpen = !!this.port;

    if (!isSocketOpen && !isPortOpen) {
      return false;
    }

    const gen = generationId !== undefined ? generationId : this.activeGenerationId;
    const envelope: WSMessage<T> = {
      version: 1,
      type,
      session_id: this.sessionId,
      generation_id: gen,
      timestamp: Date.now(),
      payload
    };

    const jsonStr = JSON.stringify(envelope);

    if (isPortOpen && this.port) {
      this.port.postMessage({ type: 'SEND', data: jsonStr });
      return true;
    }

    if (isSocketOpen && this.socket) {
      this.socket.send(jsonStr);
      return true;
    }

    return false;
  }

  public sendSchema(schema: PageScanResult): boolean {
    return this.send('FORM_SCHEMA', schema);
  }

  public sendFillResult(result: FillResult, generationId?: number): boolean {
    return this.send('FILL_RESULT', result, generationId);
  }

  public sendAudioChunk(base64Pcm: string, generationId?: number): boolean {
    return this.send('AUDIO_CHUNK', { pcm_base64: base64Pcm, generation_id: generationId ?? this.activeGenerationId }, generationId);
  }

  public sendAudio(base64Wav: string, durationMs?: number, generationId?: number): boolean {
    return this.send('AUDIO', { audio_base64: base64Wav, duration_ms: durationMs, generation_id: generationId ?? this.activeGenerationId }, generationId);
  }

  public sendTranscript(text: string, isFinal = true, generationId?: number): boolean {
    return this.send('TRANSCRIPT', { text, is_final: isFinal, generation_id: generationId ?? this.activeGenerationId }, generationId);
  }

  public sendTtsRequest(text: string, speaker?: string, generationId?: number): boolean {
    return this.send('TTS_REQUEST', { text, speaker, generation_id: generationId }, generationId);
  }

  public sendTtsCancel(requestId?: string, generationId?: number): boolean {
    return this.send('TTS_CANCEL', { request_id: requestId, generation_id: generationId ?? this.activeGenerationId }, generationId);
  }

  public sendInterrupt(generationId?: number, reason = 'user_speech_detected', timestampT0?: number): boolean {
    const gen = generationId !== undefined ? generationId : this.activeGenerationId;
    return this.send('INTERRUPT', {
      generation_id: gen,
      reason,
      timestamp_t0: timestampT0 || Date.now()
    }, gen);
  }

  private sendHello(): void {
    this.send('CLIENT_HELLO', {
      client: 'voiceform-extension',
      version: '0.1.0',
      userAgent: navigator.userAgent
    });
  }

  private handleMessage(rawText: string): void {
    try {
      const msg: WSMessage = JSON.parse(rawText);
      const msgGen: number | undefined = msg.generation_id ?? msg.payload?.generation_id;

      // Update active generation ID if incoming message is newer
      if (msgGen !== undefined && msgGen > this.activeGenerationId) {
        this.activeGenerationId = msgGen;
      }

      // Drop stale asynchronous messages if generation is older than activeGenerationId
      const isStale = msgGen !== undefined && msgGen < this.activeGenerationId;

      if (msg.type === 'SERVER_HELLO') {
        if (msg.payload?.session_id) {
          this.sessionId = msg.payload.session_id;
        }
        if (msg.payload?.current_generation_id !== undefined) {
          this.activeGenerationId = msg.payload.current_generation_id;
        }
        if (this.onConnectedCallback) {
          this.onConnectedCallback(this.sessionId);
        }
      } else if (msg.type === 'GENERATION_START') {
        if (this.onGenerationStartCallback) {
          this.onGenerationStartCallback(msg.payload);
        }
      } else if (msg.type === 'GENERATION_CANCELLED') {
        if (this.onGenerationCancelledCallback) {
          this.onGenerationCancelledCallback(msg.payload);
        }
      } else if (msg.type === 'GENERATION_COMPLETE') {
        if (!isStale && this.onGenerationCompleteCallback) {
          this.onGenerationCompleteCallback(msg.payload);
        }
      } else if (msg.type === 'TRANSCRIPT') {
        if (!isStale && this.onTranscriptReceivedCallback) {
          const text = msg.payload?.text || '';
          const lang = msg.payload?.language;
          this.onTranscriptReceivedCallback(text, lang, msgGen);
        }
      } else if (msg.type === 'AI_ACTIONS') {
        if (!isStale && this.onAiActionsReceivedCallback) {
          const actions: FormAction[] = msg.payload?.actions || [];
          this.onAiActionsReceivedCallback(actions, msgGen);
        }
      } else if (msg.type === 'AI_RESPONSE') {
        if (!isStale && this.onAiResponseReceivedCallback) {
          const responseText = msg.payload?.response || '';
          this.onAiResponseReceivedCallback(responseText, msgGen);
        }
      } else if (msg.type === 'TTS_START') {
        if (!isStale && this.onTtsStartCallback) {
          this.onTtsStartCallback(msg.payload);
        }
      } else if (msg.type === 'TTS_AUDIO') {
        if (!isStale && this.onTtsAudioCallback) {
          this.onTtsAudioCallback(msg.payload);
        }
      } else if (msg.type === 'TTS_END') {
        if (!isStale && this.onTtsEndCallback) {
          this.onTtsEndCallback(msg.payload);
        }
      } else if (msg.type === 'TTS_ERROR') {
        console.error('[VoiceForm WS] TTS error:', msg.payload);
        if (!isStale && this.onTtsErrorCallback) {
          this.onTtsErrorCallback(msg.payload);
        }
      } else if (msg.type === 'TTS_CANCEL') {
        if (this.onTtsCancelCallback) {
          this.onTtsCancelCallback(msg.payload);
        }
      } else if (msg.type === 'ASK_USER') {
        if (!isStale && this.onAskUserReceivedCallback) {
          const question = msg.payload?.message || msg.payload?.question || '';
          this.onAskUserReceivedCallback(question, msgGen);
        }
      } else if (msg.type === 'AI_ERROR') {
        console.error('[VoiceForm WS] AI Pipeline error:', msg.payload);
        if (!isStale && this.onAiErrorReceivedCallback) {
          this.onAiErrorReceivedCallback(msg.payload);
        }
      } else if (msg.type === 'FILL_ACTION') {
        if (!isStale && this.onFillActionReceivedCallback) {
          const action: FormAction = msg.payload;
          const result = this.onFillActionReceivedCallback(action, msgGen);
          this.sendFillResult(result, msgGen);
        }
      } else if (msg.type === 'FILL_ACTIONS') {
        if (!isStale && this.onFillActionsReceivedCallback) {
          const actions: FormAction[] = msg.payload?.actions || [];
          const results = this.onFillActionsReceivedCallback(actions, msgGen);
          results.forEach(r => this.sendFillResult(r, msgGen));
        }
      } else if (msg.type === 'PONG') {
        // Heartbeat acknowledged
      } else if (msg.type === 'ACK') {
        // Operation acknowledged by backend
      } else if (msg.type === 'ERROR') {
        console.error('[VoiceForm WS] Backend returned error:', msg.payload);
      }

    } catch (err) {
      console.error('[VoiceForm WS] Error parsing incoming frame:', err);
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      this.send('PING', {});
    }, 15000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return;

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectDelayMs);

    this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 1.5, this.maxReconnectDelayMs);
  }

  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    if (this.onStatusChangeCallback) {
      this.onStatusChangeCallback(status);
    }
  }
}

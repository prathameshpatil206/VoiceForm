/**
 * Browser-native Web Speech API SpeechRecognizer for VoiceForm.
 * Provides Gemini-style real-time streaming interim transcripts
 * with high accuracy, automatic punctuation, and zero server latency.
 */

export interface SpeechRecognizerOptions {
  lang?: string;
  onInterimTranscript?: (interimText: string) => void;
  onFinalTranscript?: (finalText: string) => void;
  onError?: (error: Error) => void;
  onStateChange?: (state: 'idle' | 'listening') => void;
}

export class SpeechRecognizer {
  private recognition: any = null;
  private isListening = false;
  private isIntentionallyStopped = false;
  private finalTranscript = '';
  private currentInterim = '';
  private lang: string;

  private onInterimTranscript?: (interimText: string) => void;
  private onFinalTranscript?: (finalText: string) => void;
  private onError?: (error: Error) => void;
  private onStateChange?: (state: 'idle' | 'listening') => void;

  constructor(options: SpeechRecognizerOptions = {}) {
    this.lang = options.lang || navigator.language || 'en-US';
    this.onInterimTranscript = options.onInterimTranscript;
    this.onFinalTranscript = options.onFinalTranscript;
    this.onError = options.onError;
    this.onStateChange = options.onStateChange;

    this.initRecognition();
  }

  public isSupported(): boolean {
    return typeof window !== 'undefined' && (
      'SpeechRecognition' in window || 'webkitSpeechRecognition' in window
    );
  }

  private initRecognition(): void {
    if (!this.isSupported()) return;

    const SpeechRecognitionClass =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    try {
      this.recognition = new SpeechRecognitionClass();
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.maxAlternatives = 1;
      this.recognition.lang = this.lang;

      this.recognition.onstart = () => {
        this.isListening = true;
        this.onStateChange?.('listening');
      };

      this.recognition.onresult = (event: any) => {
        let interimText = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const res = event.results[i];
          const transcript = res[0]?.transcript || '';
          if (res.isFinal) {
            this.finalTranscript = (this.finalTranscript ? `${this.finalTranscript} ` : '') + transcript.trim();
          } else {
            interimText += transcript;
          }
        }

        this.currentInterim = interimText;
        const liveCombined = (this.finalTranscript ? `${this.finalTranscript} ` : '') + interimText;
        this.onInterimTranscript?.(liveCombined.trim());
      };

      this.recognition.onerror = (event: any) => {
        // 'no-speech' and 'aborted' are non-critical standard events
        if (event.error === 'no-speech' || event.error === 'aborted') {
          return;
        }
        console.warn('[VoiceForm SpeechRecognizer] Error:', event.error);
        if (this.onError) {
          this.onError(new Error(`Speech recognition error: ${event.error}`));
        }
      };

      this.recognition.onend = () => {
        if (!this.isIntentionallyStopped && this.isListening) {
          // Keep listening continuously until user hits stop or silence duration triggers
          try {
            this.recognition.start();
            return;
          } catch {
            // Already started or restarting
          }
        }
        this.isListening = false;
        this.onStateChange?.('idle');
      };
    } catch (err: any) {
      console.warn('[VoiceForm SpeechRecognizer] Initialization failed:', err);
      this.recognition = null;
    }
  }

  public start(): boolean {
    if (!this.isSupported() || !this.recognition) {
      return false;
    }

    if (this.isListening) {
      return true;
    }

    try {
      this.finalTranscript = '';
      this.currentInterim = '';
      this.isIntentionallyStopped = false;
      this.recognition.start();
      return true;
    } catch (err: any) {
      console.warn('[VoiceForm SpeechRecognizer] start() failed:', err);
      return false;
    }
  }

  /**
   * Stops recognition and produces the full accumulated transcript.
   */
  public stop(): string {
    this.isIntentionallyStopped = true;
    this.isListening = false;

    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch {
        // Ignore if already stopped
      }
    }

    const fullText = (this.finalTranscript ? `${this.finalTranscript} ` : '') + this.currentInterim;
    const trimmed = fullText.trim();
    if (trimmed && this.onFinalTranscript) {
      this.onFinalTranscript(trimmed);
    }
    this.onStateChange?.('idle');
    return trimmed;
  }

  /**
   * Aborts recognition immediately, discarding any accumulated text.
   */
  public abort(): void {
    this.isIntentionallyStopped = true;
    this.isListening = false;
    this.finalTranscript = '';
    this.currentInterim = '';

    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch {
        // Ignore
      }
    }
    this.onStateChange?.('idle');
  }

  public getTranscript(): string {
    return ((this.finalTranscript ? `${this.finalTranscript} ` : '') + this.currentInterim).trim();
  }

  public getIsListening(): boolean {
    return this.isListening;
  }
}

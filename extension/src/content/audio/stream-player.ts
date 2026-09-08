/**
 * AudioStreamPlayer
 * Low-latency streaming audio playback engine for VoiceForm TTS with Milestone 6 Generation Synchronization.
 * Plays incoming audio chunks (PCM / MP3 / WAV) via Web Audio API,
 * maintains gapless sequential scheduling, verifies generation IDs,
 * prevents initial audio clipping via pre-warming & jitter lead time, and supports instant cancellation.
 */

export interface AudioPlayerOptions {
  onPlaybackStarted?: (generationId?: number) => void;
  onPlaybackComplete?: (generationId?: number) => void;
  onPlaybackStopped?: (generationId?: number) => void;
  onError?: (error: Error, generationId?: number) => void;
}

export class AudioStreamPlayer {
  private audioContext: AudioContext | null = null;
  private activeSources: AudioBufferSourceNode[] = [];
  private nextPlayTime = 0;
  private _isPlaying = false;
  private isStreamEnded = false;
  private currentRequestId: string | null = null;
  private currentGenerationId: number | null = null;
  private currentFormat = 'pcm';
  private currentSampleRate = 16000;
  private pcmRemainder: Uint8Array | null = null;

  private onPlaybackStartedCallback?: (generationId?: number) => void;
  private onPlaybackCompleteCallback?: (generationId?: number) => void;
  private onPlaybackStoppedCallback?: (generationId?: number) => void;
  private onErrorCallback?: (error: Error, generationId?: number) => void;

  constructor(options: AudioPlayerOptions = {}) {
    this.onPlaybackStartedCallback = options.onPlaybackStarted;
    this.onPlaybackCompleteCallback = options.onPlaybackComplete;
    this.onPlaybackStoppedCallback = options.onPlaybackStopped;
    this.onErrorCallback = options.onError;
  }

  /**
   * Pre-warms the AudioContext on user interaction (e.g. click "Start Voice").
   * Wakes up the OS/browser audio output hardware clock before speech chunks arrive,
   * completely eliminating muted or clipped initial words.
   */
  public async prewarm(): Promise<void> {
    try {
      const ctx = await this.ensureAudioContext();
      if (ctx.state === 'suspended') {
        await ctx.resume();
      }
      // Trigger a silent 1-sample buffer to engage the hardware output DAC
      const silentBuffer = ctx.createBuffer(1, 1, this.currentSampleRate);
      const source = ctx.createBufferSource();
      source.buffer = silentBuffer;
      source.connect(ctx.destination);
      source.start(0);
    } catch (err) {
      console.debug('[AudioStreamPlayer] Prewarm debug:', err);
    }
  }

  private async ensureAudioContext(): Promise<AudioContext> {
    if (!this.audioContext || this.audioContext.state === 'closed') {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      this.audioContext = new AudioContextClass();
    }
    if (this.audioContext.state === 'suspended') {
      try {
        await this.audioContext.resume();
      } catch (err) {
        console.warn('[AudioStreamPlayer] Could not resume audioContext:', err);
      }
    }
    return this.audioContext;
  }

  public isPlaying(): boolean {
    return this._isPlaying;
  }

  public getRequestId(): string | null {
    return this.currentRequestId;
  }

  public getGenerationId(): number | null {
    return this.currentGenerationId;
  }

  /**
   * Initializes a new streaming audio session for incoming chunks with generation ID tracking.
   */
  public startStream(
    requestId: string,
    format = 'pcm',
    sampleRate = 16000,
    generationId?: number
  ): void {
    // If previous audio is still playing, stop it cleanly
    if (this._isPlaying) {
      this.stop();
    }

    this.currentRequestId = requestId;
    this.currentGenerationId = generationId ?? null;
    this.currentFormat = format.toLowerCase();
    this.currentSampleRate = sampleRate;
    this.isStreamEnded = false;
    this.activeSources = [];
    this.nextPlayTime = 0;
    this.pcmRemainder = null;

    // Immediately trigger prewarm in the background
    this.prewarm().catch(() => {});
  }

  /**
   * Plays or queues an incoming base64-encoded audio chunk immediately if generation ID matches.
   */
  public async playChunk(
    base64Audio: string,
    format?: string,
    sampleRate?: number,
    isFinal = false,
    generationId?: number
  ): Promise<void> {
    // Stale generation protection: discard chunks from old/mismatched generations
    if (
      generationId !== undefined &&
      this.currentGenerationId !== null &&
      generationId !== this.currentGenerationId
    ) {
      console.debug(
        `[AudioStreamPlayer] Discarding stale chunk from gen=${generationId}, active=${this.currentGenerationId}`
      );
      return;
    }

    if (!base64Audio) {
      if (isFinal) {
        this.endStream(undefined, generationId);
      }
      return;
    }

    const fmt = (format || this.currentFormat).toLowerCase();
    const rate = sampleRate || this.currentSampleRate;

    try {
      const ctx = await this.ensureAudioContext();

      if (fmt === 'pcm') {
        this.schedulePcmChunk(ctx, base64Audio, rate);
      } else {
        await this.scheduleEncodedChunk(ctx, base64Audio);
      }

      if (isFinal) {
        this.endStream(undefined, generationId);
      }
    } catch (err: any) {
      console.error('[AudioStreamPlayer] Error playing audio chunk:', err);
      if (this.onErrorCallback) {
        this.onErrorCallback(
          err instanceof Error ? err : new Error(String(err)),
          this.currentGenerationId ?? undefined
        );
      }
    }
  }

  /**
   * Schedules a raw linear PCM chunk (16-bit little-endian) gaplessly on AudioContext.
   * Uses DataView and remainder buffering to prevent sample misalignment across chunk boundaries.
   */
  private schedulePcmChunk(ctx: AudioContext, base64Audio: string, sampleRate: number): void {
    const binaryStr = atob(base64Audio);
    let bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }

    // Prepend remainder byte from previous chunk if present
    if (this.pcmRemainder && this.pcmRemainder.length > 0) {
      const combined = new Uint8Array(this.pcmRemainder.length + bytes.length);
      combined.set(this.pcmRemainder, 0);
      combined.set(bytes, this.pcmRemainder.length);
      bytes = combined;
      this.pcmRemainder = null;
    }

    // If odd number of bytes (each 16-bit PCM sample is 2 bytes), save odd byte for next chunk
    if (bytes.length % 2 !== 0) {
      this.pcmRemainder = bytes.slice(bytes.length - 1);
      bytes = bytes.slice(0, bytes.length - 1);
    }

    if (bytes.length === 0) return;

    const numSamples = bytes.length / 2;
    const audioBuffer = ctx.createBuffer(1, numSamples, sampleRate);
    const channelData = audioBuffer.getChannelData(0);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

    for (let i = 0; i < numSamples; i++) {
      const sample = view.getInt16(i * 2, true);
      channelData[i] = sample / 32768.0;
    }

    this.scheduleBuffer(ctx, audioBuffer);
  }

  /**
   * Schedules an encoded audio chunk (MP3/WAV) by decoding with Web Audio API.
   */
  private async scheduleEncodedChunk(ctx: AudioContext, base64Audio: string): Promise<void> {
    const binaryStr = atob(base64Audio);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }

    const audioBuffer = await ctx.decodeAudioData(bytes.buffer);
    this.scheduleBuffer(ctx, audioBuffer);
  }

  /**
   * Connects buffer to destination and schedules it at nextPlayTime with smooth lead time.
   */
  private scheduleBuffer(ctx: AudioContext, buffer: AudioBuffer): void {
    const sourceNode = ctx.createBufferSource();
    sourceNode.buffer = buffer;
    sourceNode.connect(ctx.destination);

    const now = ctx.currentTime;
    // For the initial chunk, allocate a small lead time (80ms) to ensure hardware DAC is ready,
    // avoiding audio clipping or dropped initial phonemes.
    const startTime = this.nextPlayTime > now ? this.nextPlayTime : now + 0.08;
    sourceNode.start(startTime);
    this.nextPlayTime = startTime + buffer.duration;

    this.activeSources.push(sourceNode);

    if (!this._isPlaying) {
      this._isPlaying = true;
      if (this.onPlaybackStartedCallback) {
        this.onPlaybackStartedCallback(this.currentGenerationId ?? undefined);
      }
    }

    sourceNode.onended = () => {
      const idx = this.activeSources.indexOf(sourceNode);
      if (idx !== -1) {
        this.activeSources.splice(idx, 1);
      }

      // If stream ended and all scheduled chunks have completed playing
      if (this.isStreamEnded && this.activeSources.length === 0) {
        this._isPlaying = false;
        if (this.onPlaybackCompleteCallback) {
          this.onPlaybackCompleteCallback(this.currentGenerationId ?? undefined);
        }
      }
    };
  }

  /**
   * Signals that no more chunks will arrive for the current stream.
   */
  public endStream(requestId?: string, generationId?: number): void {
    if (requestId && this.currentRequestId && requestId !== this.currentRequestId) {
      return;
    }
    if (
      generationId !== undefined &&
      this.currentGenerationId !== null &&
      generationId !== this.currentGenerationId
    ) {
      return;
    }
    this.isStreamEnded = true;
    this.pcmRemainder = null;

    // If no active sources are playing, complete immediately
    if (this.activeSources.length === 0 && this._isPlaying) {
      this._isPlaying = false;
      if (this.onPlaybackCompleteCallback) {
        this.onPlaybackCompleteCallback(this.currentGenerationId ?? undefined);
      }
    }
  }

  /**
   * Immediately stops playback, cancels all scheduled buffer source nodes,
   * clears all audio queues, and resets playback state.
   */
  public stop(): number {
    const stopTimestamp = performance.now();
    const activeGen = this.currentGenerationId;

    // Stop all scheduled source nodes immediately
    for (const source of this.activeSources) {
      try {
        source.onended = null;
        source.stop(0);
        source.disconnect();
      } catch (e) {
        // Node might already be stopped
      }
    }

    this.activeSources = [];
    this.nextPlayTime = 0;
    this.isStreamEnded = true;
    this.pcmRemainder = null;
    const wasPlaying = this._isPlaying;
    this._isPlaying = false;

    if (wasPlaying && this.onPlaybackStoppedCallback) {
      this.onPlaybackStoppedCallback(activeGen ?? undefined);
    }

    return stopTimestamp;
  }

  /**
   * Reset player completely.
   */
  public reset(): void {
    this.stop();
    this.currentRequestId = null;
    this.currentGenerationId = null;
    this.isStreamEnded = false;
    this.pcmRemainder = null;
  }
}

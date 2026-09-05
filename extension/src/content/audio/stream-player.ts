/**
 * AudioStreamPlayer
 * Low-latency streaming audio playback engine for VoiceForm TTS with Milestone 6 Generation Synchronization.
 * Plays incoming audio chunks (PCM / MP3 / WAV) immediately via Web Audio API,
 * maintains gapless sequential scheduling, verifies generation IDs, and supports instant cancellation.
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

  private ensureAudioContext(): AudioContext {
    if (!this.audioContext || this.audioContext.state === 'closed') {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      this.audioContext = new AudioContextClass();
    }
    if (this.audioContext.state === 'suspended') {
      this.audioContext.resume().catch((err) => {
        console.warn('[AudioStreamPlayer] Could not resume audioContext:', err);
      });
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
      const ctx = this.ensureAudioContext();

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
   */
  private schedulePcmChunk(ctx: AudioContext, base64Audio: string, sampleRate: number): void {
    const binaryStr = atob(base64Audio);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }

    // 16-bit PCM: 2 bytes per sample
    const int16Array = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
    if (int16Array.length === 0) return;

    // Convert to Float32 [-1.0, 1.0]
    const audioBuffer = ctx.createBuffer(1, int16Array.length, sampleRate);
    const channelData = audioBuffer.getChannelData(0);
    for (let i = 0; i < int16Array.length; i++) {
      channelData[i] = int16Array[i] / 32768.0;
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
   * Connects buffer to destination and schedules it at nextPlayTime.
   */
  private scheduleBuffer(ctx: AudioContext, buffer: AudioBuffer): void {
    const sourceNode = ctx.createBufferSource();
    sourceNode.buffer = buffer;
    sourceNode.connect(ctx.destination);

    // Schedule seamlessly right after previous chunk finishes
    const now = ctx.currentTime;
    const startTime = Math.max(now, this.nextPlayTime);
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
  }
}

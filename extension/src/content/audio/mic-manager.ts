/**
 * Microphone capture and PCM streaming utility for VoiceForm.
 * Captures 16kHz mono audio from browser microphone using Web Audio API
 * and emits base64-encoded PCM audio chunks and full utterance payloads.
 */

export interface MicManagerOptions {
  sampleRate?: number;
  bufferSize?: number;
  speechThreshold?: number;
  onAudioChunk?: (base64PcmChunk: string, timestamp: number) => void;
  onSpeechActivity?: (timestamp: number, rms: number) => void;
  onAudioComplete?: (base64FullAudio: string, durationMs: number) => void;
  onError?: (error: Error) => void;
  onStateChange?: (state: 'inactive' | 'listening' | 'paused') => void;
}

export class MicrophoneManager {
  private sampleRate: number;
  private actualSampleRate = 16000;
  private bufferSize: number;
  private speechThreshold: number;
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private processorNode: ScriptProcessorNode | null = null;
  private isRecording = false;
  private recordedChunks: Float32Array[] = [];
  private totalSamples = 0;
  private startTime = 0;

  private onAudioChunk?: (base64PcmChunk: string, timestamp: number) => void;
  private onSpeechActivity?: (timestamp: number, rms: number) => void;
  private onAudioComplete?: (base64FullAudio: string, durationMs: number) => void;
  private onError?: (error: Error) => void;
  private onStateChange?: (state: 'inactive' | 'listening' | 'paused') => void;

  constructor(options: MicManagerOptions = {}) {
    this.sampleRate = options.sampleRate || 16000;
    this.bufferSize = options.bufferSize || 4096;
    this.speechThreshold = options.speechThreshold || 0.025;
    this.onAudioChunk = options.onAudioChunk;
    this.onSpeechActivity = options.onSpeechActivity;
    this.onAudioComplete = options.onAudioComplete;
    this.onError = options.onError;
    this.onStateChange = options.onStateChange;
  }

  public getIsRecording(): boolean {
    return this.isRecording;
  }

  public async startListening(): Promise<boolean> {
    if (this.isRecording) return true;

    try {
      // 1. Request microphone permission with noise suppression and echo cancellation
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      // 2. Initialize AudioContext at target sample rate if possible
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      try {
        this.audioContext = new AudioContextClass({
          sampleRate: this.sampleRate
        });
      } catch {
        // Fallback for browsers rejecting explicit sampleRate
        this.audioContext = new AudioContextClass();
      }

      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      this.actualSampleRate = this.audioContext.sampleRate || this.sampleRate;

      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.processorNode = this.audioContext.createScriptProcessor(this.bufferSize, 1, 1);

      this.recordedChunks = [];
      this.totalSamples = 0;
      this.startTime = Date.now();
      this.isRecording = true;

      this.processorNode.onaudioprocess = (e: AudioProcessingEvent) => {
        if (!this.isRecording) return;
        const now = performance.now();
        const inputData = e.inputBuffer.getChannelData(0);

        // Calculate RMS for speech activity detection on the raw input
        let sumSquares = 0;
        for (let i = 0; i < inputData.length; i++) {
          sumSquares += inputData[i] * inputData[i];
        }
        const rms = Math.sqrt(sumSquares / inputData.length);
        if (rms >= this.speechThreshold && this.onSpeechActivity) {
          this.onSpeechActivity(now, rms);
        }

        // Resample chunk to guaranteed 16,000Hz so backend VAD & Whisper never slow down or distort
        const resampledChunk = this.downsampleBuffer(inputData, this.actualSampleRate, this.sampleRate);
        this.recordedChunks.push(resampledChunk);
        this.totalSamples += resampledChunk.length;

        // Convert 16kHz chunk to 16-bit PCM base64
        const pcm16 = this.floatTo16BitPCM(resampledChunk);
        const base64Chunk = this.arrayBufferToBase64(pcm16.buffer as ArrayBuffer);
        if (this.onAudioChunk) {
          this.onAudioChunk(base64Chunk, now);
        }
      };

      this.sourceNode.connect(this.processorNode);
      // Silent GainNode before destination to keep ScriptProcessor active without feedback
      const muteNode = this.audioContext.createGain();
      muteNode.gain.value = 0.0;
      this.processorNode.connect(muteNode);
      muteNode.connect(this.audioContext.destination);

      if (this.onStateChange) {
        this.onStateChange('listening');
      }

      return true;
    } catch (err: any) {
      console.error('[VoiceForm Mic] Failed to start audio recording:', err);
      this.stopListening(true);
      if (this.onError) {
        this.onError(err instanceof Error ? err : new Error(String(err)));
      }
      return false;
    }
  }

  public stopListening(discard = false): void {
    if (!this.isRecording && !this.mediaStream) return;

    this.isRecording = false;

    // Disconnect Web Audio nodes
    try {
      if (this.processorNode) {
        this.processorNode.disconnect();
        this.processorNode.onaudioprocess = null;
        this.processorNode = null;
      }
      if (this.sourceNode) {
        this.sourceNode.disconnect();
        this.sourceNode = null;
      }
      if (this.audioContext && this.audioContext.state !== 'closed') {
        this.audioContext.close().catch(() => {});
        this.audioContext = null;
      }
    } catch (e) {
      console.warn('[VoiceForm Mic] Error closing AudioContext:', e);
    }

    // Stop mic tracks
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }

    const durationMs = Date.now() - this.startTime;

    // Produce complete WAV audio ONLY if not discarded
    if (!discard && this.totalSamples > 0 && this.onAudioComplete) {
      const merged = this.mergeChunks(this.recordedChunks, this.totalSamples);
      const wavBuffer = this.encodeWAV(merged, this.sampleRate);
      const base64Wav = this.arrayBufferToBase64(wavBuffer);
      this.onAudioComplete(base64Wav, durationMs);
    }

    this.recordedChunks = [];
    this.totalSamples = 0;

    if (this.onStateChange) {
      this.onStateChange('inactive');
    }
  }

  /**
   * High-fidelity downsampler / linear accumulator resampler.
   * Converts any hardware rate (e.g. 48kHz, 44.1kHz, 96kHz) down to target rate (16kHz).
   */
  private downsampleBuffer(buffer: Float32Array, inRate: number, outRate: number): Float32Array {
    if (inRate === outRate || inRate <= 0 || outRate <= 0) {
      return new Float32Array(buffer);
    }
    const ratio = inRate / outRate;
    const newLength = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;

    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
      let accum = 0;
      let count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i];
        count++;
      }
      result[offsetResult] = count > 0 ? accum / count : buffer[offsetBuffer];
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
    return result;
  }

  private mergeChunks(chunks: Float32Array[], totalLength: number): Float32Array {
    const result = new Float32Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      result.set(chunk, offset);
      offset += chunk.length;
    }
    return result;
  }

  private floatTo16BitPCM(input: Float32Array): Int16Array {
    const output = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return output;
  }

  private encodeWAV(samples: Float32Array, sampleRate: number): ArrayBuffer {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    // RIFF identifier
    this.writeString(view, 0, 'RIFF');
    // file length minus RIFF header
    view.setUint32(4, 36 + samples.length * 2, true);
    // RIFF type
    this.writeString(view, 8, 'WAVE');
    // format chunk identifier
    this.writeString(view, 12, 'fmt ');
    // format chunk length
    view.setUint32(16, 16, true);
    // sample format (raw PCM)
    view.setUint16(20, 1, true);
    // channel count (mono)
    view.setUint16(22, 1, true);
    // sample rate
    view.setUint32(24, sampleRate, true);
    // byte rate (sampleRate * 2 bytes * 1 channel)
    view.setUint32(28, sampleRate * 2, true);
    // block align (2 bytes)
    view.setUint16(32, 2, true);
    // bits per sample
    view.setUint16(34, 16, true);
    // data chunk identifier
    this.writeString(view, 36, 'data');
    // data chunk length
    view.setUint32(40, samples.length * 2, true);

    // Write PCM samples
    let offset = 44;
    for (let i = 0; i < samples.length; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }

    return buffer;
  }

  private writeString(view: DataView, offset: number, string: string): void {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
}

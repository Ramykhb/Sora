// Only complete, wake-prefixed commands may control the app.
export type StreamCommand = 'pause-stream' | 'resume-stream' | 'stop-stream';
export type VoiceCommand = 'start-stream' | StreamCommand | 'stop-listening' | 'start-listening';
export function voiceCommand(transcript: string): VoiceCommand | null {
  const words = transcript.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  if (/^hey sora stop listening(?: please)?$/.test(words)) return 'stop-listening';
  if (/^hey sora (?:start|resume) listening(?: please)?$/.test(words)) return 'start-listening';
  const match = /^hey sora (start|pause|resume|stop) (?:the )?stream(?: please)?$/.exec(words);
  return match ? `${match[1]}-stream` as VoiceCommand : null;
}

export type VoiceInput = { kind: 'command'; action: VoiceCommand | null } | { kind: 'question'; question: string };
export function voiceInput(transcript: string): VoiceInput | null {
  const text = transcript.trim();
  if (!text) return null;
  // Reserve the whole prefix, including commands that haven't been implemented yet.
  if (/^hey[\s,!.:;—-]+sora\b/i.test(text)) return { kind: 'command', action: voiceCommand(text) };
  return { kind: 'question', question: text };
}

// Coordinate the microphone with question recording and SORA's own audio.
export class VoiceAudioGate {
  private holders = new Set<symbol>();
  private listeners = new Set<() => void>();
  get paused() { return this.holders.size > 0; }
  subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }
  suspend() {
    const id = Symbol();
    this.holders.add(id);
    this.listeners.forEach(listener => listener());
    return () => {
      if (this.holders.delete(id)) this.listeners.forEach(listener => listener());
    };
  }
}
export const voiceAudioGate = new VoiceAudioGate();

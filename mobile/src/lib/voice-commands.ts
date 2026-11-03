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

// Question recording owns the microphone; answer playback keeps recognition active.
export class VoiceAudioGate {
  private holders = new Set<symbol>();
  private listeners = new Set<() => void>();
  private playbacks = new Map<symbol, string>();
  private recentPlayback: { text: string; until: number }[] = [];
  get playing() { return this.playbacks.size > 0; }
  playback(text: string) {
    const id = Symbol();
    this.playbacks.set(id, text);
    this.listeners.forEach(listener => listener());
    return () => {
      if (!this.playbacks.delete(id)) return;
      // Recognition can deliver a few late speaker results after playback ends.
      this.recentPlayback = this.recentPlayback.filter(value => value.until > Date.now());
      this.recentPlayback.push({ text, until: Date.now() + 700 });
      this.listeners.forEach(listener => listener());
    };
  }
  get playbackTexts() {
    this.recentPlayback = this.recentPlayback.filter(value => value.until > Date.now());
    return [...this.playbacks.values(), ...this.recentPlayback.map(value => value.text)];
  }
  userTranscript(transcript: string, utterancePlayback: readonly string[] = []) {
    const tokens = (value: string) => [...value.toLocaleLowerCase().matchAll(/[\p{L}\p{N}]+/gu)];
    const heard = tokens(transcript);
    if (!heard.length) return '';
    const sources = [...this.playbackTexts, ...utterancePlayback];
    let prefix = 0;
    for (const text of sources) {
      const spoken = tokens(text).map(value => value[0]);
      for (let start = 0; start < spoken.length; start++) {
        let length = 0;
        while (start + length < spoken.length && length < heard.length && spoken[start + length] === heard[length][0]) length++;
        prefix = Math.max(prefix, length);
      }
    }
    if (prefix === heard.length) return '';
    // Shared wake words must stay attached to a genuinely new app command.
    if (voiceInput(transcript)?.kind === 'command') return transcript.trim();
    // A cumulative result may contain a speaker echo followed by the user's voice.
    return prefix >= 3 ? transcript.slice(heard[prefix].index).trim() : transcript.trim();
  }
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

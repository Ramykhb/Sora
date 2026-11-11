// Stream/listening controls require Hey Sora; explicit playback/SOS phrases work directly.
export type StreamCommand = 'pause-stream' | 'resume-stream' | 'stop-stream';
export type PlaybackCommand = 'repeat-answer' | 'repeat-directions' | 'stop-speaking';
export type VoiceCommand = 'start-stream' | StreamCommand | PlaybackCommand | 'stop-listening' | 'start-listening' | 'mute' | 'unmute' | 'send-sos-location';
function playbackCommand(transcript: string): PlaybackCommand | null {
  const words = transcript.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim().replace(/^hey sora /, '');
  if (/^(?:repeat (?:that|(?:the |my |your )?(?:last )?answer)|say that again)(?: please)?$/.test(words)) return 'repeat-answer';
  if (/^repeat (?:the |my |your )?(?:last )?(?:directions|route)(?: please)?$/.test(words)) return 'repeat-directions';
  if (/^stop (?:speaking|talking|audio)(?: please)?$/.test(words)) return 'stop-speaking';
  return null;
}
export function isSOSLocationCommand(transcript: string) {
  const words = transcript.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  if (/^(?:hey sora )?(?:(?:send|share) (?:an? |my )?)?(?:sos|s o s)(?: (?:to )?(?:(?:my|the) )?(?:emergency )?contact)?(?: please)?$/.test(words)) return true;
  return /^(?:hey sora )?(?:send|share) (?:my |the )?location (?:to|with) (?:my |the )?(?:sos|s o s|emergency) contact(?: please)?$/.test(words);
}
export function voiceCommand(transcript: string): VoiceCommand | null {
  if (isSOSLocationCommand(transcript)) return 'send-sos-location';
  const playback = playbackCommand(transcript);
  if (playback) return playback;
  const words = transcript.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  if (/^hey sora stop listening(?: please)?$/.test(words)) return 'stop-listening';
  if (/^hey sora (?:start|resume) listening(?: please)?$/.test(words)) return 'start-listening';
  const voice = /^hey sora (mute|unmute)(?: (?:your )?voice)?(?: please)?$/.exec(words);
  if (voice) return voice[1] as 'mute' | 'unmute';
  const match = /^hey sora (start|pause|resume|stop) (?:the )?stream(?: please)?$/.exec(words);
  return match ? `${match[1]}-stream` as VoiceCommand : null;
}

export type VoiceInput = { kind: 'command'; action: VoiceCommand | null } | { kind: 'question'; question: string };
export function voiceInput(transcript: string): VoiceInput | null {
  const text = transcript.trim();
  if (!text) return null;
  if (isSOSLocationCommand(text)) return { kind: 'command', action: 'send-sos-location' };
  const playback = playbackCommand(text);
  if (playback) return { kind: 'command', action: playback };
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
  private recognitionState: 'off' | 'starting' | 'ready' = 'off';
  private recognitionReadyAt = 0;
  get recognitionExpected() { return this.recognitionState !== 'off'; }
  setRecognitionState(state: 'off' | 'starting' | 'ready') {
    if (state === this.recognitionState) return;
    this.recognitionState = state;
    if (state === 'ready') this.recognitionReadyAt = Date.now();
    this.listeners.forEach(listener => listener());
  }
  waitForRecognitionReady(timeoutMs = 2000): Promise<boolean> {
    if (this.recognitionState === 'off') return Promise.resolve(false);
    return new Promise(resolve => {
      let settled = false;
      let settleTimer: ReturnType<typeof setTimeout> | undefined;
      let deadline: ReturnType<typeof setTimeout> | undefined;
      let unsubscribe = () => {};
      const finish = (ready: boolean) => {
        if (settled) return;
        settled = true; clearTimeout(settleTimer); clearTimeout(deadline); unsubscribe();
        resolve(ready);
      };
      const check = () => {
        clearTimeout(settleTimer);
        if (this.recognitionState === 'off') { finish(false); return; }
        if (this.recognitionState !== 'ready') return;
        // Route/voice-processing changes settle before the first audible word.
        const remaining = 150 - (Date.now() - this.recognitionReadyAt);
        if (remaining <= 0) finish(true);
        else settleTimer = setTimeout(check, remaining);
      };
      unsubscribe = this.subscribe(check);
      deadline = setTimeout(() => finish(false), timeoutMs);
      check();
    });
  }
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

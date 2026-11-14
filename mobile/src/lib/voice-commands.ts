// Stream/listening controls require the SORA wake word; explicit playback/SOS phrases work directly.
// Commands are understood in English, Arabic and French, in every combination of script and accents.
export type StreamCommand = 'pause-stream' | 'resume-stream' | 'stop-stream';
export type PlaybackCommand = 'repeat-answer' | 'repeat-directions' | 'stop-speaking';
export type VoiceCommand = 'start-stream' | StreamCommand | PlaybackCommand | 'stop-listening' | 'start-listening' | 'mute' | 'unmute' | 'send-sos-location';
const ARABIC_MARKS = /[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]/g;
// "Hey Sora", "Hé Sora", "يا سورا" and common recognizer spellings of them.
const WAKE = /^(?:(?:hey|he|hay)\s+sora|(?:يا|هي|هيا|هاي)\s+سور[اىي])(?=\s|$)/;
const PLEASE = '(?: please| s il te plait| s il vous plait| من فضلك| لو سمحت)?';
const at = (body: string) => new RegExp(`^(?:${body})${PLEASE}$`);
function normalize(transcript: string) {
  return transcript
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(ARABIC_MARKS, '')
    .replace(/[أإآٱ]/g, 'ا')
    .replace(/ى/g, 'ي')
    .replace(/ة/g, 'ه')
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
function parse(transcript: string) {
  const words = normalize(transcript);
  const wake = WAKE.test(words);
  return { wake, words: wake ? words.replace(WAKE, '').trim() : words };
}
export function hasSORAWakeWord(transcript: string) { return WAKE.test(normalize(transcript)); }
function playbackCommand(transcript: string): PlaybackCommand | null {
  const { words } = parse(transcript);
  if (at('repeat (?:that|(?:the |my |your )?(?:last )?answer)|say that again|(?:repete|redis) (?:ca|ceci|la reponse|la derniere reponse|encore|le dernier message)|اعد (?:الاجابه|الاخيره|الجواب|ذلك|ما قلته)|اعد مره اخري|قل ذلك مره اخري').test(words)) return 'repeat-answer';
  if (at('repeat (?:the |my |your )?(?:last )?(?:directions|route)|(?:repete|redis) (?:les |mes |tes |l )?(?:dernieres? )?(?:directions|itineraire|route|chemin)|اعد (?:ال)?(?:اتجاهات|مسار|مسارك|طريق|خط السير)').test(words)) return 'repeat-directions';
  if (at('stop (?:speaking|talking|audio)|arrete (?:de parler|de lire|l audio|la voix)|tais toi|توقف عن (?:الكلام|التحدث)|اوقف (?:الصوت|الكلام)').test(words)) return 'stop-speaking';
  return null;
}
export function isSOSLocationCommand(transcript: string) {
  const { words } = parse(transcript);
  if (at('(?:(?:send|share) (?:an? |my )?)?(?:sos|s o s)(?: (?:to )?(?:(?:my|the) )?(?:emergency )?contact)?').test(words)) return true;
  if (at('(?:send|share) (?:my |the )?location (?:to|with) (?:my |the )?(?:sos|s o s|emergency) contact').test(words)) return true;
  if (at('(?:envoie|lance|partage|transmets) (?:un |le )?(?:sos|signal de detresse)(?: (?:a|au) (?:mon |le )?contact(?: d urgence| urgence)?)?').test(words)) return true;
  if (at('(?:envoie|partage|transmets) (?:ma |la )?position (?:a|au|avec) (?:mon |le |la )?contact(?: d urgence| urgence| sos)').test(words)) return true;
  return at('(?:ارسل|ابعث|شارك) (?:(?:موقعي|الموقع) (?:الي|الى|ل|مع) (?:ال)?جهه (?:اتصال|الاتصال)(?: (?:ال)?طواري)?|(?:رساله |اشاره )?استغاثه)|اس او اس|sos').test(words);
}
export function voiceCommand(transcript: string): VoiceCommand | null {
  if (isSOSLocationCommand(transcript)) return 'send-sos-location';
  const playback = playbackCommand(transcript);
  if (playback) return playback;
  const { wake, words } = parse(transcript);
  if (!wake) return null;
  if (at('stop listening|arrete (?:d ecouter|l ecoute)|توقف عن (?:ال)?استماع|(?:اوقف|ايقاف|الغ|الغي) (?:ال)?استماع').test(words)) return 'stop-listening';
  if (at('(?:start|resume) listening|(?:commence|reprends|continue|active|demarre) (?:a |l )?(?:ecouter|ecoute)|(?:ابدا|استانف|تابع|واصل|اكمل|اعد|شغل) (?:ال)?استماع').test(words)) return 'start-listening';
  if (at('unmute(?: (?:your )?voice)?|(?:retablis|reactive|rallume|active|remets) (?:le |la )?(?:son|audio|voix)|(?:الغ|الغي|فك) (?:ال)?كتم(?: (?:ال)?صوت)?|(?:شغل|اشغل|فعل) (?:ال)?صوت').test(words)) return 'unmute';
  if (at('mute(?: (?:your )?voice)?|(?:coupe|mets|desactive|baisse) (?:le |la )?(?:son|audio|voix)(?: en sourdine)?|sourdine|silence|(?:اكتم|كتم) (?:ال)?صوت|صامت').test(words)) return 'mute';
  if (at('pause (?:the )?stream|(?:mets|met) (?:le |la )?(?:flux|stream|direct) en pause|(?:pause|pauses) (?:le |la )?(?:flux|stream|direct)|(?:اوقف|ايقاف|علق) (?:ال)?بث موقتا').test(words)) return 'pause-stream';
  if (at('resume (?:the )?stream|(?:reprends|reprend|reprendre|continue|relance) (?:le |la )?(?:flux|stream|direct)|(?:reprise) (?:du |le )?(?:flux|stream|direct)|(?:استانف|استئناف|تابع|واصل|اكمل) (?:ال)?بث(?: المباشر)?').test(words)) return 'resume-stream';
  if (at('stop (?:the )?stream|(?:arrete|stoppe|termine) (?:le |la )?(?:flux|stream|direct)|(?:اوقف|ايقاف|انهي|انهاء|اغلق) (?:ال)?بث(?: المباشر)?').test(words)) return 'stop-stream';
  if (at('start (?:the )?stream|(?:demarre|commence|lance) (?:le |la )?(?:flux|stream|direct)|(?:ابدا|ابدء|اشغل|شغل) (?:ال)?بث(?: المباشر)?').test(words)) return 'start-stream';
  return null;
}

export type VoiceInput = { kind: 'command'; action: VoiceCommand | null } | { kind: 'question'; question: string };
export function voiceInput(transcript: string): VoiceInput | null {
  const text = transcript.trim();
  if (!text) return null;
  if (isSOSLocationCommand(text)) return { kind: 'command', action: 'send-sos-location' };
  const playback = playbackCommand(text);
  if (playback) return { kind: 'command', action: playback };
  // Reserve the whole prefix, including commands that haven't been implemented yet.
  if (hasSORAWakeWord(text)) return { kind: 'command', action: voiceCommand(text) };
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

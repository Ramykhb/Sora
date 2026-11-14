// Stream/listening controls require the SORA wake word; explicit playback/SOS phrases work directly.
// Commands are understood in English, Arabic and French, in every combination of script and accents.
export type StreamCommand = 'pause-stream' | 'resume-stream' | 'stop-stream';
export type PlaybackCommand = 'repeat-answer' | 'repeat-directions' | 'next-step' | 'previous-step' | 'show-full-route' | 'stop-speaking';
export type VoiceCommand = 'start-stream' | StreamCommand | PlaybackCommand | 'stop-listening' | 'start-listening' | 'mute' | 'unmute' | 'send-sos-location';
const ARABIC_MARKS = /[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]/g;
// "Hey Sora", "Hé Sora", "يا سورا" and common recognizer spellings of them.
const WAKE = /^(?:hey|he|hay|يا|هي|هيا|هاي)\s*(?:sora|[سص]ور[ايه]|سار[اه])(?=\s|$)/;
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
  if (at('(?:next|the next) step|(?:etape suivante|prochaine etape)|(?:الخطوه التاليه|الخطوه القادمه)').test(words)) return 'next-step';
  if (at('(?:previous|the previous|last) step|(?:etape precedente)|الخطوه السابقه').test(words)) return 'previous-step';
  if (at('show (?:me )?(?:the )?(?:full|entire) route|(?:affiche|montre) (?:moi )?(?:l |le )?(?:itineraire|trajet) (?:complet|entier)|(?:اعرض|اظهر) (?:المسار|الطريق) (?:كاملا|بالكامل)').test(words)) return 'show-full-route';
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
  if (at('stop (?:the )?stream|(?:arrete|stoppe|termine) (?:le |la )?(?:flux|stream|direct)|(?:اوقف|وقف|ايقاف|انهي|انهاء|اغلق) (?:ال)?بث(?: المباشر)?').test(words)) return 'stop-stream';
  if (at('start (?:the )?stream|(?:demarre|commence|lance) (?:le |la )?(?:flux|stream|direct)|(?:ابدا|ابدء|بلش)(?: (?:ال)?بث(?: المباشر)?)?|(?:اشغل|شغل) (?:ال)?بث(?: المباشر)?').test(words)) return 'start-stream';
  return null;
}

export type VoiceInput = { kind: 'command'; action: VoiceCommand | null } | { kind: 'question'; question: string };
export function voiceInput(transcript: string): VoiceInput | null {
  const text = transcript.trim();
  if (!text) return null;
  if (isSOSLocationCommand(text)) return { kind: 'command', action: 'send-sos-location' };
  const playback = playbackCommand(text);
  if (playback) return { kind: 'command', action: playback };
  // Alert memories are backend requests, even when addressed to Sora. Other
  // wake-prefixed phrases still belong to the local app-command dispatcher.
  if (hasSORAWakeWord(text)) {
    const words = parse(text).words;
    if (/^(?:please )?(?:(?:alert|notify|tell|warn) me|let me know) (?:when|if|whenever|once|on|upon)(?: |$)|^(?:alerte moi|previens moi|avertis moi) (?:quand|si|lorsque)(?: |$)|^(?:نبهني|اخبرني|حذرني) (?:عندما|اذا|لما)(?: |$)/.test(words)) {
      return { kind: 'question', question: text };
    }
    return { kind: 'command', action: voiceCommand(text) };
  }
  return { kind: 'question', question: text };
}

// TTS expands distances and step numbers; STT may return either their spoken
// words or digits. Canonicalize only for echo comparison, retaining offsets so
// a real question/command after a speaker prefix keeps its original spelling.
const NUMBER_WORDS: Record<string, number> = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7,
  eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13,
  fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18,
  nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60,
  seventy: 70, eighty: 80, ninety: 90,
};
function playbackTokens(value: string) {
  const words = [...value.matchAll(/[\p{L}][\p{L}\p{M}]*|[\p{N}]+(?:[.,٫][\p{N}]+)*/gu)]
    .map(match => ({ text: /^\p{N}/u.test(match[0])
      ? match[0].replace(/[٠-٩]/g, digit => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
        .replace(/,(?=\d{3}(?:\D|$))/g, '').replace(/[,٫]/g, '.')
      : normalize(match[0]), index: match.index }));
  const result: { text: string; index: number }[] = [];
  for (let i = 0; i < words.length; i++) {
    const start = words[i];
    if (Object.hasOwn(NUMBER_WORDS, start.text)) {
      let whole = 0, group = 0;
      while (i < words.length) {
        const word = words[i].text;
        if (Object.hasOwn(NUMBER_WORDS, word)) group += NUMBER_WORDS[word];
        else if (word === 'hundred') group *= 100;
        else if (word === 'thousand') { whole += group * 1000; group = 0; }
        else if (!(word === 'and' && Object.hasOwn(NUMBER_WORDS, words[i + 1]?.text))) break;
        i++;
      }
      let number = String(whole + group);
      if (words[i]?.text === 'point') {
        number += '.'; i++;
        while (i < words.length && (Object.hasOwn(NUMBER_WORDS, words[i].text)
          ? NUMBER_WORDS[words[i].text] < 10 : /^\d+$/.test(words[i].text))) {
          number += Object.hasOwn(NUMBER_WORDS, words[i].text) ? NUMBER_WORDS[words[i].text] : words[i].text;
          i++;
        }
      }
      result.push({ text: number, index: start.index }); i--;
    } else {
      const text = /^(?:kilomet(?:er|re)s?|كيلومتر|كيلومترات)$/.test(start.text) ? 'km'
        : /^(?:met(?:er|re)s?|متر|امتار)$/.test(start.text) ? 'm' : start.text;
      result.push({ text, index: start.index });
    }
  }
  return result;
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
    const heard = playbackTokens(transcript);
    if (!heard.length) return '';
    const sources = [...this.playbackTexts, ...utterancePlayback];
    let prefix = 0;
    for (const text of sources) {
      const spoken = playbackTokens(text).map(value => value.text);
      for (let start = 0; start < spoken.length; start++) {
        let length = 0;
        while (start + length < spoken.length && length < heard.length) {
          const source = spoken[start + length], recognized = heard[length].text;
          // A partial result can stop halfway through a spoken decimal.
          const decimalPrefix = length === heard.length - 1 && /^\d+(?:\.\d*)?$/.test(recognized)
            && source.startsWith(recognized + (recognized.includes('.') ? '' : '.'));
          if (source !== recognized && !decimalPrefix) break;
          length++;
        }
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

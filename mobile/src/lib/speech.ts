import { setAudioModeAsync } from 'expo-audio';
import * as Speech from 'expo-speech';
import { SpeechController } from './speech-policy';
import { voiceAudioGate } from './voice-commands';
import { speechText } from './voice-language';
import { serverSpeech } from './server-speech';

let audioGeneration = 0;
let releaseAudio: (() => void) | undefined;
let arabicVoice: Promise<string | undefined> | undefined;
// Prefer an installed Enhanced Arabic voice; compact fallback voices are the
// usual cause of clipped or mispronounced Arabic on iOS.
function preferredArabicVoice() {
  arabicVoice ??= Speech.getAvailableVoicesAsync().then(voices => {
    const arabic = voices.filter(voice => voice.language.toLowerCase().startsWith('ar'));
    return arabic.sort((a, b) =>
      Number(b.quality === 'Enhanced') - Number(a.quality === 'Enhanced')
      || Number(b.language.toLowerCase() === 'ar-sa') - Number(a.language.toLowerCase() === 'ar-sa'),
    )[0]?.identifier;
  }).catch(() => undefined);
  return arabicVoice;
}
export const speech = new SpeechController({
  async stop() {
    audioGeneration++;
    serverSpeech.stop();
    const release = releaseAudio;
    releaseAudio = undefined;
    try { await Speech.stop(); } finally { release?.(); }
  },
  async speak(text, options) {
    const generation = ++audioGeneration;
    releaseAudio?.();
    const release = voiceAudioGate.playback(text);
    releaseAudio = release;
    const done = (callback?: () => void) => {
      release();
      if (releaseAudio === release) releaseAudio = undefined;
      callback?.();
    };
    try {
      // Reuse the recognizer's active session. Changing its route at utterance
      // start, or speaking before a restart is ready, can soften the first words.
      let audioReady: Promise<void> | undefined;
      const prepareAudio = () => audioReady ??= (async () => {
        const recognitionReady = await voiceAudioGate.waitForRecognitionReady();
        if (generation !== audioGeneration) return;
        if (!recognitionReady) {
          await setAudioModeAsync({ allowsRecording: voiceAudioGate.recognitionExpected, playsInSilentMode: true });
        }
      })();
      const language = options.language.toLowerCase().split('-')[0];
      if (language === 'ar' && !options.urgent) {
        const handled = await serverSpeech.speak(speechText(text, options.language), {
          onDone: () => done(options.onDone),
          onError: error => done(() => options.onError?.(error)),
        }, prepareAudio);
        if (generation !== audioGeneration) { done(); return; }
        if (handled) return;
      }
      await prepareAudio();
      if (generation !== audioGeneration) { done(); return; }
      const voice = language === 'ar' ? await preferredArabicVoice() : undefined;
      if (generation !== audioGeneration) { done(); return; }
      Speech.speak(speechText(text, options.language), {
        ...options, volume: 1, useApplicationAudioSession: true,
        ...(voice ? { voice } : {}),
        ...(language === 'ar' ? { rate: 1.25 } : {}),
        onDone: () => done(options.onDone), onStopped: () => done(options.onStopped), onError: error => done(() => options.onError?.(error)),
      });
    } catch (error) { done(); throw error; }
  },
});

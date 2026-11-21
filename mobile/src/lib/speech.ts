import { setAudioModeAsync } from 'expo-audio';
import * as Speech from 'expo-speech';
import { SpeechController } from './speech-policy';
import { voiceAudioGate } from './voice-commands';
import { speechText } from './voice-language';
import { serverSpeech } from './server-speech';
import { arabicRecordings, arabicAlertRecording } from './arabic-recordings';

let audioGeneration = 0;
let releaseAudio: (() => void) | undefined;
export const speech = new SpeechController({
  async stop() {
    audioGeneration++;
    serverSpeech.stop();
    arabicRecordings.stop();
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
      let deviceVoice: Speech.Voice | undefined;
      if (language === 'ar') {
        const callbacks = {
          onDone: () => done(options.onDone),
          onError: (error: Error) => done(() => options.onError?.(error)),
        };
        // Urgent camera warnings use bundled recordings of the same female
        // voice. They must not wait for a cloud request or change to device TTS.
        if (options.urgent && !options.dynamicAlert) {
          await prepareAudio();
          if (generation !== audioGeneration) { done(); return; }
          arabicRecordings.speak(arabicAlertRecording(text), callbacks);
          return;
        }
        let handled = false;
        try { handled = await serverSpeech.speak(speechText(text, options.language), callbacks, prepareAudio); }
        catch { /* A failure before playback may still use the device's Arabic voice. */ }
        if (generation !== audioGeneration) { done(); return; }
        if (handled) return;
        const voices = await Speech.getAvailableVoicesAsync().catch(() => []);
        if (generation !== audioGeneration) { done(); return; }
        const preferred = options.language.toLowerCase();
        deviceVoice = voices.filter(voice => /^ar(?:[-_]|$)/i.test(voice.language)).sort((a, b) =>
          Number(b.language.toLowerCase() === preferred) - Number(a.language.toLowerCase() === preferred)
          || Number(b.quality === Speech.VoiceQuality.Enhanced) - Number(a.quality === Speech.VoiceQuality.Enhanced)
        )[0];
        if (!deviceVoice) {
          await prepareAudio();
          if (generation !== audioGeneration) { done(); return; }
          arabicRecordings.speak('unavailable', callbacks);
          return;
        }
      }
      await prepareAudio();
      if (generation !== audioGeneration) { done(); return; }
      Speech.speak(speechText(text, options.language), {
        ...options, volume: 1, useApplicationAudioSession: true,
        ...(deviceVoice ? { voice: deviceVoice.identifier, language: deviceVoice.language } : {}),
        onDone: () => done(options.onDone), onStopped: () => done(options.onStopped), onError: error => done(() => options.onError?.(error)),
      });
    } catch (error) { done(); throw error; }
  },
});

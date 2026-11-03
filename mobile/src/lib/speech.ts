import { setAudioModeAsync } from 'expo-audio';
import * as Speech from 'expo-speech';
import { SpeechController } from './speech-policy';
import { voiceAudioGate } from './voice-commands';

let audioGeneration = 0;
let releaseAudio: (() => void) | undefined;
export const speech = new SpeechController({
  async stop() {
    audioGeneration++;
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
      const recognitionReady = await voiceAudioGate.waitForRecognitionReady();
      if (generation !== audioGeneration) { done(); return; }
      if (!recognitionReady) {
        await setAudioModeAsync({ allowsRecording: voiceAudioGate.recognitionExpected, playsInSilentMode: true });
      }
      if (generation !== audioGeneration) { done(); return; }
      Speech.speak(text, { ...options, volume: 1, useApplicationAudioSession: true, onDone: () => done(options.onDone), onStopped: () => done(options.onStopped), onError: error => done(() => options.onError?.(error)) });
    } catch (error) { done(); throw error; }
  },
});

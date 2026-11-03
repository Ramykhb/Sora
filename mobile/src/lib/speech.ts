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
      // Full-duplex audio keeps recognition and its echo cancellation running
      // while answers remain audible in iPhone silent mode.
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      if (generation !== audioGeneration) { done(); return; }
      Speech.speak(text, { ...options, useApplicationAudioSession: true, onDone: () => done(options.onDone), onStopped: () => done(options.onStopped), onError: error => done(() => options.onError?.(error)) });
    } catch (error) { done(); throw error; }
  },
});

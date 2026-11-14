import { createAudioPlayer } from 'expo-audio';
import { voiceAudioGate } from './voice-commands';

const clips = {
  obstacle: {
    text: 'يوجد جسم في وسط صورة الكاميرا. لا يمكنني تقييم المسار كاملاً.',
    source: require('../../assets/audio/ar/obstacle.mp3'),
  },
  closedDoor: {
    text: 'يبدو أن هناك باباً مغلقاً في وسط صورة الكاميرا.',
    source: require('../../assets/audio/ar/closed-door.mp3'),
  },
  unavailable: {
    text: 'الصوت غير متاح حالياً. الإجابة ظاهرة على الشاشة.',
    source: require('../../assets/audio/ar/unavailable.mp3'),
  },
};
export type ArabicRecording = keyof typeof clips;
export function arabicAlertRecording(text: string): ArabicRecording {
  return text === clips.closedDoor.text ? 'closedDoor' : 'obstacle';
}
let active: (() => void) | undefined;
export const arabicRecordings = {
  stop() { const cleanup = active; active = undefined; cleanup?.(); },
  speak(key: ArabicRecording, callbacks: { onDone?: () => void; onError?: (error: Error) => void }) {
    arabicRecordings.stop();
    const clip = clips[key];
    const player = createAudioPlayer(clip.source, { keepAudioSessionActive: true });
    const release = voiceAudioGate.playback(clip.text);
    let cleaned = false;
    const subscription = player.addListener('playbackStatusUpdate', status => {
      if (cleaned || (!status.didJustFinish && !status.error)) return;
      cleanup();
      if (status.error) callbacks.onError?.(new Error('Arabic audio playback failed'));
      else callbacks.onDone?.();
    });
    const cleanup = () => {
      if (cleaned) return;
      cleaned = true;
      if (active === cleanup) active = undefined;
      subscription.remove();
      try { player.pause(); player.remove(); } finally { release(); }
    };
    active = cleanup;
    try { player.volume = 1; player.play(); }
    catch (error) { cleanup(); throw error; }
  },
};

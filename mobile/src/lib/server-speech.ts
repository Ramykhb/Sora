import { createAudioPlayer } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';
import type { ApiClient } from './api';

type Callbacks = { onDone?: () => void; onError?: (error: Error) => void };
let client: Pick<ApiClient, 'response'> | null = null;
let generation = 0;
let dispose: (() => void) | undefined;

// One cancellable player shared by automatic answers and spoken app feedback.
export const serverSpeech = {
  configure(api: Pick<ApiClient, 'response'> | null) {
    client = api;
    return () => {
      if (client === api) { client = null; serverSpeech.stop(); }
    };
  },
  stop() {
    generation++;
    const cleanup = dispose;
    dispose = undefined;
    cleanup?.();
  },
  async speak(text: string, callbacks: Callbacks): Promise<boolean> {
    if (!client) return false;
    serverSpeech.stop();
    const current = generation;
    try {
      const response = await client.response('/speech/synthesis', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, language: 'ar', provider: 'gemini' }),
      });
      if (current !== generation) return true;
      const data = await response.arrayBuffer();
      if (current !== generation) return true;
      let uri: string;
      let clearMedia: () => void;
      if (Platform.OS === 'web') {
        uri = URL.createObjectURL(new Blob([data], { type: 'audio/wav' }));
        clearMedia = () => URL.revokeObjectURL(uri);
      } else {
        const file = new File(Paths.cache, `sora-speech-${Date.now()}-${current}.wav`);
        clearMedia = () => { if (file.exists) file.delete(); };
        try { await file.write(new Uint8Array(data)); }
        catch (error) { clearMedia(); throw error; }
        uri = file.uri;
      }
      if (current !== generation) { clearMedia(); return true; }
      let player: ReturnType<typeof createAudioPlayer>;
      try { player = createAudioPlayer({ uri }); }
      catch (error) { clearMedia(); throw error; }
      let settled = false;
      const subscription = player.addListener('playbackStatusUpdate', status => {
        if (settled || (!status.didJustFinish && !status.error)) return;
        settled = true;
        cleanup();
        if (current !== generation) return;
        if (status.error) callbacks.onError?.(new Error('Arabic audio playback failed'));
        else callbacks.onDone?.();
      });
      const cleanup = () => {
        settled = true;
        if (dispose === cleanup) dispose = undefined;
        subscription.remove();
        try { player.pause(); player.remove(); } finally { clearMedia(); }
      };
      dispose = cleanup;
      player.volume = 1;
      player.play();
      return true;
    } catch {
      if (current !== generation) return true;
      dispose?.(); dispose = undefined;
      // Network/provider failures fall back to the installed device voice.
      return false;
    }
  },
};

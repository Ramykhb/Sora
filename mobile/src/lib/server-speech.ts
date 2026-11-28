import { createAudioPlaylist } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import { fetch as streamingFetch } from 'expo/fetch';
import { Platform } from 'react-native';
import type { ApiClient } from './api';

type Callbacks = { onDone?: () => void; onError?: (error: Error) => void };
let client: Pick<ApiClient, 'response'> | null = null;
let generation = 0;
let dispose: (() => void) | undefined;

// Queue small WAV segments as the server generates them. Native HTTP media players
// otherwise buffer a complete short answer before playing it.
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
  async speak(text: string, callbacks: Callbacks, beforePlay: () => Promise<void> = async () => {}, language = 'ar'): Promise<boolean> {
    if (!client) return false;
    const api = client;
    serverSpeech.stop();
    const current = generation;
    const controller = new AbortController();
    const files: File[] = [];
    let playlist: ReturnType<typeof createAudioPlaylist>;
    try { playlist = createAudioPlaylist({ updateInterval: 100 }); }
    catch { return false; }
    let settled = false;
    let started = false;
    let completed = false;
    let drained = false;
    let queued = 0;
    let resolveStart: (handled: boolean) => void = () => {};
    const start = new Promise<boolean>(resolve => { resolveStart = resolve; });
    const startupTimer = setTimeout(() => fail(new Error('Speech startup timed out')), 8000);
    // Long answers are generated sentence by sentence, so only a stalled stream times out.
    let networkTimer: ReturnType<typeof setTimeout>;
    const awaitNetwork = () => {
      clearTimeout(networkTimer);
      networkTimer = setTimeout(() => fail(new Error('Speech stream timed out')), 22000);
    };
    awaitNetwork();
    const subscription = playlist.addListener('playlistStatusUpdate', status => {
      if (settled) return;
      if (status.playing) { started = true; clearTimeout(startupTimer); resolveStart(true); }
      if (status.didJustFinish) { drained = true; if (completed) finish(); }
    });
    const cleanup = () => {
      if (settled) return;
      settled = true;
      if (dispose === cancel) dispose = undefined;
      clearTimeout(startupTimer); clearTimeout(networkTimer);
      controller.abort(); subscription.remove();
      try { playlist.pause(); playlist.destroy(); }
      finally { files.forEach(file => { if (file.exists) file.delete(); }); }
    };
    const cancel = () => { cleanup(); resolveStart(true); };
    const finish = () => { cleanup(); resolveStart(true); callbacks.onDone?.(); };
    const fail = (error: Error) => {
      if (settled) return;
      cleanup(); resolveStart(started);
      if (started) callbacks.onError?.(error);
    };
    dispose = cancel;
    playlist.volume = 1;

    async function frame(line: string) {
      if (settled || current !== generation || !line.trim()) return;
      awaitNetwork();
      const value: { type: string; data?: string } = JSON.parse(line);
      if (value.type === 'done') { completed = true; if (drained) finish(); return; }
      if (completed || value.type !== 'audio' || !value.data || value.data.length > 100000) throw new Error('Invalid audio frame');
      let uri: string;
      if (Platform.OS === 'web') uri = `data:audio/wav;base64,${value.data}`;
      else {
        const file = new File(Paths.cache, `sora-speech-${current}-${queued}.wav`);
        files.push(file);
        await file.write(value.data, { encoding: 'base64' });
        if (settled || current !== generation) { if (file.exists) file.delete(); return; }
        uri = file.uri;
      }
      const resume = queued === 0 || drained;
      queued++; drained = false;
      playlist.add({ uri });
      if (resume) {
        await beforePlay();
        if (!settled && current === generation) playlist.play();
      }
    }

    async function consume() {
      try {
        const response = await api.response('/speech/stream', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, language }), signal: controller.signal,
        }, streamingFetch);
        if (settled || current !== generation) return;
        const reader = response.body?.getReader();
        if (!reader) throw new Error('Audio streaming is unavailable');
        const decoder = new TextDecoder();
        let buffer = '';
        while (!settled) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value, { stream: !done });
          if (buffer.length > 256000) throw new Error('Audio frame exceeds limit');
          let newline: number;
          while (!settled && (newline = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
            await frame(line);
          }
          if (done) break;
        }
        if (settled) return;
        if (buffer.trim()) await frame(buffer);
        if (!completed || !queued) throw new Error('Incomplete audio stream');
        clearTimeout(networkTimer);
      } catch (error) {
        if (!settled && current === generation) fail(error instanceof Error ? error : new Error('Speech failed'));
      }
    }
    void consume();
    return start;
  },
};

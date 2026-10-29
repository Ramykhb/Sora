import { useEffect, useRef, useState } from 'react';
import { Platform, Text, View } from 'react-native';
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from 'expo-audio';
import { File } from 'expo-file-system';
import * as Speech from 'expo-speech';
import { useAuth } from '@/providers/auth';
import type { Answer, Language, Scope } from '@/lib/api';
import { Action, ui } from './controls';

export function VoiceQuestion({ sessionId, language, scope, onAnswer, onError, disabled }: { sessionId: string; language: Language; scope: Scope; onAnswer: (answer: Answer) => void; onError: (message: string) => void; disabled: boolean }) {
  const { api } = useAuth();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const stopping = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (recorder.isRecording) void recorder.stop().then(() => {
        if (recorder.uri && Platform.OS !== 'web') new File(recorder.uri).delete();
      }).catch(() => {}).finally(() => setAudioModeAsync({ allowsRecording: false }).catch(() => {}));
    };
  }, [recorder]);
  async function toggle() {
    if (stopping.current) return;
    setBusy(true); onError('');
    let uploadedUri: string | null = null;
    try {
      if (!recorder.isRecording) {
        await Speech.stop();
        const permission = await AudioModule.requestRecordingPermissionsAsync();
        if (!permission.granted) throw new Error('Microphone access is required for voice questions.');
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
        await recorder.prepareToRecordAsync();
        recorder.record();
      } else {
        stopping.current = true;
        await recorder.stop();
        await setAudioModeAsync({ allowsRecording: false });
        if (!recorder.uri) throw new Error('No recording was captured.');
        uploadedUri = recorder.uri;
        const form = new FormData();
        if (Platform.OS === 'web') {
          const blob = await (await fetch(recorder.uri)).blob();
          form.append('audio', blob, blob.type.includes('mp4') ? 'question.m4a' : 'question.webm');
        } else form.append('audio', { uri: recorder.uri, name: 'question.m4a', type: 'audio/mp4' } as unknown as Blob);
        form.append('language', language); form.append('scope', scope);
        const answer = await api.upload<Answer>(`/sessions/${sessionId}/questions/audio`, form);
        if (mounted.current) onAnswer(answer);
      }
    } catch (e) {
      await setAudioModeAsync({ allowsRecording: false }).catch(() => {});
      if (mounted.current) onError(e instanceof Error ? e.message : 'Voice question failed.');
    } finally {
      if (uploadedUri) {
        try { if (Platform.OS === 'web') URL.revokeObjectURL(uploadedUri); else new File(uploadedUri).delete(); } catch { /* The OS may already have removed the temporary recording. */ }
      }
      stopping.current = false; if (mounted.current) setBusy(false);
    }
  }
  // Bound recordings below the server duration limit, including forgotten recordings.
  useEffect(() => { if (state.isRecording && state.durationMillis >= 55000 && !stopping.current) void toggle(); });
  return <View style={{ gap: 8 }}><Action title={busy ? 'Processing voice…' : state.isRecording ? 'Stop recording and ask Sora' : 'Ask with your voice'} disabled={busy || disabled} onPress={() => void toggle()} />{state.isRecording && <Text style={ui.copy}>Recording · {Math.round(state.durationMillis / 1000)}s</Text>}</View>;
}

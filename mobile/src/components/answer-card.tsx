import { useEffect, useRef, useState } from 'react';
import { Platform, Text, View } from 'react-native';
import { useAudioPlayer, setAudioModeAsync } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import * as Speech from 'expo-speech';
import type { Answer } from '@/lib/api';
import { useAuth } from '@/providers/auth';
import { Action, ui } from './controls';
export function AnswerCard({ answer, onError }: { answer: Answer; onError: (message: string) => void }) {
  const { api } = useAuth();
  const player = useAudioPlayer(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');
  const media = useRef<string | File | null>(null);
  const mounted = useRef(true);
  function clearMedia() {
    if (typeof media.current === 'string') URL.revokeObjectURL(media.current);
    else if (media.current?.exists) media.current.delete();
    media.current = null;
  }
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; clearMedia(); }; }, []);
  async function audio() {
    setBusy(true);
    try {
      await Speech.stop(); await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      // Fetch through the shared client so expired credentials and speech errors are handled.
      const response = await api.response(`/sessions/${answer.session_id}/questions/${answer.id}/audio`);
      const data = await response.arrayBuffer();
      if (!mounted.current) return;
      player.pause(); player.replace(null); clearMedia();
      let uri: string;
      if (Platform.OS === 'web') {
        uri = URL.createObjectURL(new Blob([data], { type: 'audio/wav' })); media.current = uri;
      } else {
        const file = new File(Paths.cache, `sora-${answer.id}.wav`);
        await file.write(new Uint8Array(data)); media.current = file; uri = file.uri;
      }
      if (!mounted.current) { clearMedia(); return; }
      player.replace({ uri }); player.play();
    } catch (e) { if (mounted.current) onError(e instanceof Error ? e.message : 'Audio playback failed'); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <View style={ui.card}><Text style={ui.subtitle}>{answer.question}</Text><Text style={ui.copy}>{answer.answer}</Text>{answer.uncertain && <Text style={ui.copy}>Sora is uncertain about this answer.</Text>}{answer.processing_warnings.map(w => <Text key={w} style={ui.error}>{w}</Text>)}<Text style={ui.copy}>{new Date(answer.created_at).toLocaleString()} · {answer.evidence_frame_ids.length} evidence images</Text>
    <View style={ui.row}><Action title="Read aloud" onPress={() => { void Speech.stop(); Speech.speak(answer.answer, { language: answer.language }); }} /><Action title="Server voice" disabled={busy} onPress={() => void audio()} /><Action title="Stop audio" onPress={() => { player.pause(); void Speech.stop(); }} /></View>
    <View style={ui.row}>{(['correct', 'incorrect', 'unsure'] as const).map(rating => <Action key={rating} disabled={busy} title={`${feedback === rating ? '✓ ' : ''}${rating}`} onPress={() => {
      setBusy(true); void api.request(`/sessions/${answer.session_id}/questions/${answer.id}/feedback`, 'POST', { rating }).then(() => setFeedback(rating)).catch(e => onError(e.message)).finally(() => setBusy(false));
    }} />)}</View>
  </View>;
}

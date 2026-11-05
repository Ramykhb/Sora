import { useEffect, useRef, useState } from 'react';
import { Platform, View } from 'react-native';
import { useAudioPlayer, useAudioPlayerStatus, setAudioModeAsync } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import { voiceAudioGate } from '@/lib/voice-commands';
import { speech } from '@/lib/speech';
import type { Answer } from '@/lib/api';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import { Card, Icon, Label } from './sora-ui';
import { Action, useUI } from './controls';
export function AnswerCard({ answer, onError }: { answer: Answer; onError: (message: string) => void }) {
  const ui = useUI();
  const { api } = useAuth();
  const { preferences, colors } = usePreferences();
  const player = useAudioPlayer(null);
  const playback = useAudioPlayerStatus(player);
  useEffect(() => {
    if (playback.playing) return voiceAudioGate.playback(answer.answer);
  }, [playback.playing, answer.answer]);
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
  const playbackGeneration = useRef(0);
  useEffect(() => speech.registerInterruptor(() => { playbackGeneration.current++; player.pause(); }), [player]);
  async function audio() {
    if (speech.isMuted) return;
    setBusy(true);
    try {
      await speech.stop();
      const generation = playbackGeneration.current;
      const recognitionReady = await voiceAudioGate.waitForRecognitionReady();
      if (!mounted.current || generation !== playbackGeneration.current) return;
      if (!recognitionReady) await setAudioModeAsync({ allowsRecording: voiceAudioGate.recognitionExpected, playsInSilentMode: true });
      // Fetch through the shared client so expired credentials and speech errors are handled.
      const response = await api.response(`/sessions/${answer.session_id}/questions/${answer.id}/audio`);
      const data = await response.arrayBuffer();
      if (!mounted.current || generation !== playbackGeneration.current) return;
      player.pause(); player.replace(null); clearMedia();
      let uri: string;
      if (Platform.OS === 'web') {
        uri = URL.createObjectURL(new Blob([data], { type: 'audio/wav' })); media.current = uri;
      } else {
        const file = new File(Paths.cache, `sora-${answer.id}.wav`);
        await file.write(new Uint8Array(data)); media.current = file; uri = file.uri;
      }
      if (!mounted.current || generation !== playbackGeneration.current) { clearMedia(); return; }
      player.replace({ uri }); player.play();
    } catch (e) { if (mounted.current) onError(e instanceof Error ? e.message : 'Audio playback failed'); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <Card style={{ gap: 14 }}><View style={{ flexDirection: 'row', gap: 9, alignItems: 'flex-start' }}><Icon name="mic-outline" size={18} color={colors.accent} /><View style={{ flex: 1, gap: 5 }}><Label muted size={10}>YOU ASKED</Label><Label bold size={15}>{answer.question}</Label></View></View><View style={{ backgroundColor: colors.elevated, borderRadius: 12, padding: 14, gap: 9 }}><View style={{ flexDirection: 'row', gap: 7, alignItems: 'center' }}><Icon name="sparkles-outline" size={15} /><Label bold size={10} style={{ color: colors.primary }}>SORA</Label></View><Label size={14} selectable>{answer.answer}</Label></View>{answer.uncertain && <Label muted size={12}>Sora is uncertain about this answer.</Label>}{answer.processing_warnings.map(w => <Label key={w} style={{ color: colors.danger }}>{w}</Label>)}<Label muted size={10}>{new Date(answer.created_at).toLocaleString()} · {answer.evidence_frame_ids.length} evidence images</Label>
    <View style={ui.row}><Action title="Read aloud" disabled={!preferences.speak} onPress={() => void speech.answer(answer.answer, answer.language)} /><Action title="Server voice" disabled={busy || !preferences.speak} onPress={() => void audio()} /><Action title="Stop audio" onPress={() => void speech.stop()} /></View>
    <View style={ui.row}>{(['correct', 'incorrect', 'unsure'] as const).map(rating => <Action key={rating} disabled={busy} title={`${feedback === rating ? '✓ ' : ''}${rating}`} onPress={() => {
      setBusy(true); void api.request(`/sessions/${answer.session_id}/questions/${answer.id}/feedback`, 'POST', { rating }).then(() => setFeedback(rating)).catch(e => onError(e.message)).finally(() => setBusy(false));
    }} />)}</View>
  </Card>;
}

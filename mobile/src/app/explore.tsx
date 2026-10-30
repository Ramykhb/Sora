import { useCallback, useState } from 'react';
import { Alert, Platform, ScrollView, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { router, useFocusEffect } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '@/providers/auth';
import type { Answer, CaptureSession, Frame } from '@/lib/api';
import { AuthScreen } from '@/components/auth-screen';
import { AnswerCard } from '@/components/answer-card';
import { Action, Field, ui } from '@/components/controls';

export default function MomentsScreen() {
  const { tokens } = useAuth();
  return tokens ? <Moments key={tokens.user.id} /> : <AuthScreen />;
}
function Moments() {
  const { api } = useAuth();
  const [sessions, setSessions] = useState<CaptureSession[]>([]);
  const [selected, setSelected] = useState<CaptureSession | null>(null);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [history, setHistory] = useState<Answer[]>([]);
  const [query, setQuery] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(false);
  const [headers, setHeaders] = useState<Record<string, string>>({});
  const [original, setOriginal] = useState(false);
  async function run(work: () => Promise<void>) {
    setBusy(true); setError('');
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : 'Request failed'); } finally { setBusy(false); }
  }
  useFocusEffect(useCallback(() => {
    let cancelled = false;
    void api.request<CaptureSession[]>('/sessions?limit=200').then(value => { if (!cancelled) setSessions(value); }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [api]));
  function bounds() {
    const params = new URLSearchParams();
    for (const [key, value] of [['since', since], ['until', until]]) if (value.trim()) {
      const date = new Date(value);
      if (!Number.isFinite(date.getTime())) throw new Error(`Enter a valid ${key} date/time.`);
      params.set(key, date.toISOString());
    }
    return params;
  }
  async function load(session: CaptureSession, search = false, append = false) {
    const params = bounds();
    const offset = append ? frames.length : 0;
    params.set('limit', search ? '10' : '50');
    params.set('offset', String(offset));
    if (search) params.set('q', query.trim());
    const path = `/sessions/${session.id}`;
    const [result, answers, token] = await Promise.all([
      search ? api.request<{ frames: Frame[]; warnings: string[] }>(`${path}/frames/search?${params}`) : api.request<Frame[]>(`${path}/frames?${params}`),
      api.request<Answer[]>(`${path}/questions?limit=200`), api.token(),
    ]);
    const values = Array.isArray(result) ? result : result.frames;
    if (!Array.isArray(result) && result.warnings.length) setError(result.warnings.join('\n'));
    setHeaders({ Authorization: `Bearer ${token}` });
    setSelected(session); setFrames(previous => append ? [...previous, ...values] : values); setHistory(answers); setMore(!search && values.length === 50);
  }
  function confirmDelete(title: string, work: () => Promise<void>) {
    if (Platform.OS === 'web') { if (window.confirm(title)) void run(work); }
    else Alert.alert(title, 'This permanently deletes the selected retained data.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: () => void run(work) }]);
  }
  return <SafeAreaView style={ui.screen}><ScrollView contentContainerStyle={ui.content} keyboardShouldPersistTaps="handled">
    <Action title="Back to Sora" onPress={() => router.replace('/')} /><Text style={ui.title}>Moments</Text>
    {!!error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    {!selected ? <><Text style={ui.copy}>Choose a retained session.</Text>{sessions.length === 0 && <Text style={ui.copy}>No retained sessions yet.</Text>}{sessions.map(session => <Action key={session.id} title={`${new Date(session.created_at).toLocaleString()} · ${session.status}`} disabled={busy} onPress={() => void run(() => load(session))} />)}</> : <>
      <Text style={ui.subtitle}>{new Date(selected.created_at).toLocaleString()}</Text>
      <Action title="Choose another session" disabled={busy} onPress={() => { setSelected(null); setFrames([]); setHistory([]); }} />
      <Field placeholder="Search visual memory" value={query} onChangeText={setQuery} />
      <Field placeholder="Since (optional, e.g. 2026-10-29T09:00)" value={since} onChangeText={setSince} autoCapitalize="none" />
      <Field placeholder="Until (optional)" value={until} onChangeText={setUntil} autoCapitalize="none" />
      <Action title="Search memory" disabled={busy || !query.trim()} onPress={() => void run(() => load(selected, true))} />
      <Action title="Show timeline" disabled={busy} onPress={() => void run(() => load(selected))} />
      <Action title={original ? 'Show enhanced images' : 'Show original images'} onPress={() => setOriginal(value => !value)} />
      {frames.length === 0 && <Text style={ui.copy}>No matching retained images.</Text>}
      {frames.map(frame => <View style={ui.card} key={frame.id}>
        <Image source={{ uri: api.url(`/sessions/${selected.id}/frames/${frame.id}/image?original=${original}`), headers }} cachePolicy="none" style={{ width: '100%', height: 210, borderRadius: 14 }} contentFit="contain" accessibilityLabel={frame.caption || 'Retained camera frame'} onError={() => setError('Image unavailable. Refresh the timeline to renew access.')} />
        <Text style={ui.copy}>{new Date(frame.captured_at).toLocaleString()}</Text><Text style={ui.subtitle}>{frame.caption || (frame.enrichment_status === 'pending' ? 'Frame saved. AI description is being prepared.' : 'Caption unavailable')}</Text>
        {!!frame.ocr_text && <Text style={ui.copy}>Text: {frame.ocr_text}</Text>}
        <Text style={ui.copy}>{frame.detected_objects.map(o => `${o.label} (${Math.round(o.confidence * 100)}%)`).join(', ')}</Text>
        {frame.processing_warnings.map(w => <Text key={w} style={ui.error}>{w}</Text>)}
        <Action title="Delete image" disabled={busy} onPress={() => confirmDelete('Delete this image?', async () => { await api.request(`/sessions/${selected.id}/frames/${frame.id}`, 'DELETE'); setFrames(previous => previous.filter(f => f.id !== frame.id)); })} />
      </View>)}
      {more && <Action title="Load more images" disabled={busy} onPress={() => void run(() => load(selected, false, true))} />}
      <Text style={ui.subtitle}>Conversation history</Text>{history.map(answer => <AnswerCard key={answer.id} answer={answer} onError={setError} />)}
      <Action title="Delete this session and all its data" disabled={busy} onPress={() => confirmDelete('Delete this session?', async () => { await api.request(`/sessions/${selected.id}`, 'DELETE'); setSessions(previous => previous.filter(s => s.id !== selected.id)); setSelected(null); setFrames([]); setHistory([]); })} />
    </>}
  </ScrollView></SafeAreaView>;
}

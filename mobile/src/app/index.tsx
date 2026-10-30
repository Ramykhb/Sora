import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, ScrollView, Switch, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useFocusEffect } from 'expo-router';
import * as Speech from 'expo-speech';
import { useAuth } from '@/providers/auth';
import { ApiError, type Answer, type CaptureSession, type Frame, type Language, type Scope } from '@/lib/api';
import { connectLive } from '@/lib/live';
import { AuthScreen } from '@/components/auth-screen';
import { Action, Field, ui } from '@/components/controls';
import { StreamStatus } from '@/components/stream-status';
import { LiveCamera } from '@/components/live-camera';
import { VoiceQuestion } from '@/components/voice-question';
import { AnswerCard } from '@/components/answer-card';

export default function HomeScreen() {
  const { tokens } = useAuth();
  return tokens ? <Assistant key={tokens.user.id} /> : <AuthScreen />;
}
function Assistant() {
  const { api, tokens } = useAuth();
  const [session, setSession] = useState<CaptureSession | null>(null);
  const [sessions, setSessions] = useState<CaptureSession[]>([]);
  const [consent, setConsent] = useState(false);
  const [language, setLanguage] = useState<Language>('en');
  const [scope, setScope] = useState<Scope>('recent');
  const [alerts, setAlerts] = useState(false);
  const [speak, setSpeak] = useState(true);
  const [active, setActive] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const [focused, setFocused] = useState(true);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState('');
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [connection, setConnection] = useState('');
  const spoken = useRef(new Set<string>());
  const selectedId = useRef<string | null>(null);
  const select = useCallback((value: CaptureSession | null) => {
    selectedId.current = value?.id || null;
    setActive(false); setAnswers([]); setFrame(null); setSession(value);
    if (value) { setLanguage(value.language); setAlerts(value.alerts_enabled); }
    void Speech.stop();
  }, []);
  const fail = useCallback((e: unknown) => {
    setError(e instanceof Error ? e.message : 'Request failed.');
    if (e instanceof ApiError && e.status === 404) select(null);
  }, [select]);
  const listSessions = useCallback(() => {
    void api.request<CaptureSession[]>('/sessions?limit=50').then(setSessions).catch(fail);
  }, [api, fail]);
  useFocusEffect(useCallback(() => { setFocused(true); listSessions(); return () => { setFocused(false); void Speech.stop(); }; }, [listSessions]));
  useEffect(() => {
    const subscription = AppState.addEventListener('change', value => { setForeground(value === 'active'); if (value !== 'active') void Speech.stop(); });
    return () => subscription.remove();
  }, []);
  useEffect(() => {
    if (!session) return;
    const timer = setTimeout(() => { setActive(false); select(null); setNotice('This session expired. Start a new session.'); listSessions(); }, Math.max(0, Date.parse(session.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [session, select, listSessions]);
  const receiveAnswer = useCallback((answer: Answer, readAloud = false) => {
    if (answer.session_id !== selectedId.current) return;
    setAnswers(previous => [answer, ...previous.filter(value => value.id !== answer.id)]);
    if (readAloud && speak && !spoken.current.has(answer.id)) {
      spoken.current.add(answer.id); void Speech.stop(); Speech.speak(answer.answer, { language: answer.language });
    }
  }, [speak]);
  useEffect(() => {
    if (!session || !foreground || !focused) return;
    let cancelled = false;
    const path = `/sessions/${session.id}`;
    const sync = () => {
      void Promise.all([api.request<Answer[]>(`${path}/questions`), api.request<Frame[]>(`${path}/frames?limit=1`)]).then(([history, frames]) => {
        if (cancelled) return;
        setAnswers(previous => [...new Map([...history, ...previous].map(a => [a.id, a])).values()].sort((a, b) => b.created_at.localeCompare(a.created_at)));
        setFrame(frames[0] || null);
      }).catch(e => { if (!cancelled) fail(e); });
    };
    sync();
    const live = connectLive(api, `${path}/events`, event => {
      if (event.type === 'ready') sync();
      if (event.type === 'session_updated' && event.session) {
        setSession(event.session); setLanguage(event.session.language); setAlerts(event.session.alerts_enabled);
        if (event.session.status !== 'active') setActive(false);
      }
      if (event.frame) {
        const incoming = event.frame;
        setFrame(previous => !previous || previous.id === incoming.id || Date.parse(incoming.captured_at) >= Date.parse(previous.captured_at) ? incoming : previous);
      }
      if (event.question) receiveAnswer(event.question, true);
      if (event.type === 'frame_rejected') setNotice(`Frame skipped: ${event.reason}`);
      if (event.type === 'processing_error') setError(event.message || event.code || 'Frame processing failed');
      if (event.type === 'alert' && event.message) {
        setNotice(event.message);
        if (speak && alerts) Speech.speak(event.message, { language: event.language || language });
      }
    }, setConnection);
    return () => { cancelled = true; live.close(); };
  }, [api, session, foreground, focused, receiveAnswer, fail, speak, alerts, language]);
  async function run(operation: () => Promise<void>) {
    setBusy(true); setError('');
    try { await operation(); } catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function ask() {
    if (!session || !question.trim()) return;
    const answer = await api.request<Answer>(`/sessions/${session.id}/questions`, 'POST', { question, scope, language });
    receiveAnswer(answer, true); setQuestion('');
  }
  async function preferences(nextLanguage: Language, nextAlerts: boolean) {
    if (session) setSession(await api.request<CaptureSession>(`/sessions/${session.id}`, 'PATCH', { language: nextLanguage, alerts_enabled: nextAlerts }));
    setLanguage(nextLanguage); setAlerts(nextAlerts);
  }
  return <SafeAreaView style={ui.screen}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={ui.content}>
    <View style={ui.row}><Text style={[ui.title, { flex: 1 }]}>sora</Text><Action title="Moments" onPress={() => router.push('/explore')} /><Action title="Settings" onPress={() => router.push('./settings')} /></View>
    <Text style={ui.subtitle}>Hello, {tokens?.user.display_name}</Text>
    <Text style={ui.copy}>{new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</Text>
    {!!error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    {!!notice && <Text accessibilityLiveRegion="polite" style={ui.copy}>{notice}</Text>}
    <View style={ui.row}>{(['en', 'fr', 'ar'] as const).map(value => <Action key={value} title={`${language === value ? '✓ ' : ''}${{ en: 'English', fr: 'Français', ar: 'العربية' }[value]}`} disabled={busy || session?.status === 'closed'} onPress={() => void run(() => preferences(value, alerts))} />)}</View>
    <View style={ui.row}><Switch accessibilityLabel="Spoken answers" value={speak} onValueChange={value => { setSpeak(value); if (!value) void Speech.stop(); }} /><Text style={ui.copy}>Speak answers</Text><Switch accessibilityLabel="Obstacle alerts" disabled={busy || session?.status === 'closed'} value={alerts} onValueChange={value => void run(() => preferences(language, value))} /><Text style={ui.copy}>Obstacle alerts</Text></View>
    {!session ? <View style={ui.card}>
      <Text style={ui.subtitle}>Start live assistance</Text><Text style={ui.copy}>Camera frames are analyzed and selected images and conversations are retained until the session expires. Voice uploads are processed without being retained.</Text>
      <View style={ui.row}><Switch accessibilityLabel="Consent to camera processing and retention" value={consent} onValueChange={setConsent} /><Text style={[ui.copy, { flex: 1 }]}>I consent to camera processing and visual memory storage.</Text></View>
      <Action title={busy ? 'Starting…' : 'Start a new session'} disabled={!consent || busy} onPress={() => void run(async () => {
        const created = await api.request<CaptureSession>('/sessions', 'POST', { consent: true, language, alerts_enabled: alerts });
        select(created); setActive(true); listSessions();
      })} />
      <Action title="Refresh sessions" onPress={listSessions} />
      {sessions.map(item => <Action key={item.id} title={`${new Date(item.created_at).toLocaleString()} · ${item.status}`} onPress={() => select(item)} />)}
    </View> : <>
      <Text style={ui.copy}>Session · {session.status} · expires {new Date(session.expires_at).toLocaleString()} · {connection}</Text>
      {session.status === 'active' && <><LiveCamera key={`${session.id}-${foreground}-${focused}-${active}`} sessionId={session.id} active={active && foreground && focused} />{active && foreground && focused && <StreamStatus sessionId={session.id} onUnavailable={fail} />}<Action title={active ? 'Pause assistance' : 'Resume assistance'} onPress={() => setActive(v => !v)} /></>}
      {frame && <View style={ui.card}><Text style={ui.subtitle}>Latest scene</Text><Text style={ui.copy}>{frame.caption || (frame.enrichment_status === 'pending' ? 'Frame saved. AI description is being prepared.' : 'Caption unavailable')}</Text>{!!frame.ocr_text && <Text style={ui.copy}>Text: {frame.ocr_text}</Text>}<Text style={ui.copy}>{new Date(frame.captured_at).toLocaleTimeString()}</Text>{frame.processing_warnings.map(w => <Text key={w} style={ui.error}>{w}</Text>)}</View>}
      <View style={ui.row}>{(['recent', 'memory', 'auto'] as const).map(value => <Action key={value} title={`${scope === value ? '✓ ' : ''}${value === 'recent' ? 'Current view' : value === 'memory' ? 'Memory' : 'Auto'}`} onPress={() => setScope(value)} />)}</View>
      <Field placeholder="Ask about your surroundings or memory" value={question} onChangeText={setQuestion} multiline maxLength={2000} />
      <Action title={busy ? 'Thinking…' : 'Ask Sora'} disabled={busy || !question.trim()} onPress={() => void run(ask)} />
      {foreground && focused && <VoiceQuestion key={session.id} sessionId={session.id} language={language} scope={scope} disabled={busy} onAnswer={answer => receiveAnswer(answer, true)} onError={setError} />}
      <Action title="Stop speaking" onPress={() => void Speech.stop()} />
      {answers.length === 0 && <Text style={ui.copy}>Your conversation will appear here.</Text>}
      {answers.map(answer => <AnswerCard key={answer.id} answer={answer} onError={setError} />)}
      {session.status === 'active' && <Action title="End capture and keep memory" disabled={busy} onPress={() => void run(async () => { setActive(false); setSession(await api.request<CaptureSession>(`/sessions/${session.id}/close`, 'POST')); listSessions(); })} />}
      <Action title="Choose another session" disabled={busy} onPress={() => { select(null); listSessions(); }} />
    </>}
  </ScrollView></SafeAreaView>;
}

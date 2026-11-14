import { ScreenIntro, SoraLogo } from '@/components/brand';
import { BottomNav, Card, Icon, Label, Page } from '@/components/sora-ui';
import { usePreferences } from '@/providers/preferences';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Switch, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { speech } from '@/lib/speech';
import { questionLocation } from '@/lib/question-location';
import { useHandsFreeQuestions, useVoiceCommands, useVoiceStreamControls } from '@/providers/voice-commands';
import { useAuth } from '@/providers/auth';
import { ApiError, type Answer, type CaptureSession, type Frame, type Language, type Scope, type Observation } from '@/lib/api';
import { connectLive } from '@/lib/live';
import { AuthScreen } from '@/components/auth-screen';
import { Action, Field, useUI } from '@/components/controls';
import { VoiceWaveform } from '@/components/voice-waveform';
import { StreamStatus } from '@/components/stream-status';
import { LiveCamera } from '@/components/live-camera';
import { VoiceQuestion } from '@/components/voice-question';
import { AnswerCard } from '@/components/answer-card';

export default function HomeScreen() {
  const { tokens } = useAuth();
  return tokens ? <Assistant key={tokens.user.id} /> : <AuthScreen />;
}
function Assistant() {
  const ui = useUI();
  const { api, tokens } = useAuth();
  const [session, setSession] = useState<CaptureSession | null>(null);
  const [sessions, setSessions] = useState<CaptureSession[]>([]);
  const [consent, setConsent] = useState(false);
  const [language, setLanguage] = useState<Language>('en');
  const [scope, setScope] = useState<Scope>('recent');
  const [alerts, setAlerts] = useState(false);
  const { preferences: appPreferences, update, colors } = usePreferences();
  const speak = appPreferences.speak;
  const setSpeak = (value: boolean) => update({ speak: value });
  const [active, setActive] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const [focused, setFocused] = useState(true);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState('');
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [observation, setObservation] = useState<Observation | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [connection, setConnection] = useState('');
  const voice = useVoiceCommands();
  const voicePending = useRef(false);
  const closingStream = useRef(false);
  const spoken = useRef(new Set<string>());
  const selectedId = useRef<string | null>(null);
  const select = useCallback((value: CaptureSession | null) => {
    selectedId.current = value?.id || null;
    setActive(false); setAnswers([]); setFrame(null); setObservation(null); setSession(value);
    if (value) { setLanguage(value.language); setAlerts(value.alerts_enabled); }
    void speech.stop();
  }, []);
  const fail = useCallback((e: unknown) => {
    setError(e instanceof Error ? e.message : 'Request failed.');
    if (e instanceof ApiError && e.status === 404) select(null);
  }, [select]);
  const listSessions = useCallback(() => {
    void api.request<CaptureSession[]>('/sessions?limit=50').then(setSessions).catch(fail);
  }, [api, fail]);
  useFocusEffect(useCallback(() => { setFocused(true); listSessions(); return () => { setFocused(false); void speech.stop(); }; }, [listSessions]));
  useEffect(() => {
    const subscription = AppState.addEventListener('change', value => { setForeground(value === 'active'); if (value !== 'active') void speech.stop(); });
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
    speech.rememberAnswer(answer.answer, answer.language);
    if (readAloud && !voicePending.current && speak && !spoken.current.has(answer.id)) {
      spoken.current.add(answer.id); void speech.answer(answer.answer, answer.language);
    }
  }, [speak]);
  useEffect(() => {
    if (!foreground || !focused) void speech.stop();
  }, [foreground, focused]);
  useEffect(() => {
    if (!observation) return;
    const timer = setTimeout(() => setObservation(null), Math.max(0, Date.parse(observation.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [observation]);
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
      if (event.type === 'observation' && active && event.expires_at && Date.parse(event.expires_at) > Date.now()) {
        setObservation(event as Observation & typeof event);
      }
      if (event.type === 'frame_rejected') setNotice(`Frame skipped: ${event.reason}`);
      if (event.type === 'processing_error') setError(event.message || event.code || 'Frame processing failed');
      if (event.type === 'detection_error') setError('Live detection is unavailable. Check the server.');
      if (event.type === 'alert' && event.message && active && event.expires_at && Date.parse(event.expires_at) > Date.now()) {
        setNotice(event.message);
        if (speak && alerts && event.id) void speech.alert(event.id, event.message, event.language || language, event.expires_at);
      }
    }, setConnection);
    return () => { cancelled = true; live.close(); };
  }, [api, session, foreground, focused, receiveAnswer, fail, speak, alerts, language, active]);
  async function run(operation: () => Promise<void>) {
    setBusy(true); setError('');
    try { await operation(); } catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function ask() {
    if (!session || !question.trim()) return;
    const answer = await api.request<Answer>(`/sessions/${session.id}/questions`, 'POST', { question, scope, language, location: await questionLocation(question) });
    receiveAnswer(answer, true); setQuestion('');
  }
  useHandsFreeQuestions(async question => {
    if (!session) throw new Error('Say Hey Sora, start stream first. Then ask about your surroundings.');
    if (scope === 'recent' && !active) throw new Error('Your stream is paused. Say Hey Sora, resume stream first.');
    if (busy) throw new Error('Please wait for the current request to finish, then ask again.');
    voicePending.current = true; setBusy(true); setError('');
    try {
      const answer = await api.request<Answer>(`/sessions/${session.id}/questions`, 'POST', { question, scope, language, location: await questionLocation(question) });
      spoken.current.add(answer.id);
      receiveAnswer(answer);
      return answer;
    } finally { voicePending.current = false; setBusy(false); }
  }, `${session?.id}:${scope}:${language}:${active}`);
  useVoiceStreamControls(async command => {
    if (closingStream.current) throw new Error('Your stream is stopping. Please wait.');
    if (!session || session.status !== 'active') throw new Error('There is no active stream. Say Hey Sora, start stream first.');
    if (command === 'pause-stream') {
      setActive(false); setObservation(null);
      return active ? 'Stream paused. Say Hey Sora, resume stream when you are ready.' : 'Your stream is already paused.';
    }
    if (command === 'resume-stream') {
      setActive(true);
      if (!focused) router.navigate('/assistant');
      return active && focused ? 'Your stream is already running.' : 'Resuming your stream.';
    }
    closingStream.current = true;
    setActive(false); setObservation(null);
    try {
      setSession(await api.request<CaptureSession>(`/sessions/${session.id}/close`, 'POST'));
      listSessions();
      return 'Stream stopped. Your saved moments are still available.';
    } finally { closingStream.current = false; }
  }, !!session && session.status === 'active', !active);
  async function preferences(nextLanguage: Language, nextAlerts: boolean) {
    if (session) setSession(await api.request<CaptureSession>(`/sessions/${session.id}`, 'PATCH', { language: nextLanguage, alerts_enabled: nextAlerts }));
    setLanguage(nextLanguage); setAlerts(nextAlerts);
  }
  return <Page title="Ask Sora" footer={<BottomNav active="Assist" />}>
    <ScreenIntro eyebrow="Voice & vision" title={`Hello, ${tokens?.user.display_name || 'there'}.`} subtitle="Ask a question. Get a little more clarity." />
    {!!error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    {!!notice && <Text accessibilityLiveRegion="polite" style={ui.copy}>{notice}</Text>}
    <Card><View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}><Icon name="options-outline" size={20} /><Label bold size={14}>Assistance preferences</Label></View><View style={ui.row}>{(['en', 'fr', 'ar'] as const).map(value => <Action key={value} title={`${language === value ? '✓ ' : ''}${{ en: 'English', fr: 'Français', ar: 'العربية' }[value]}`} disabled={busy || session?.status === 'closed'} onPress={() => void run(() => preferences(value, alerts))} />)}</View>
    <View style={{ gap: 10 }}><View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}><Label size={13} style={{ flex: 1 }}>Speak answers</Label><Switch accessibilityLabel="Spoken answers" value={speak} trackColor={{ false: colors.trackOff, true: colors.primary }} onValueChange={value => { setSpeak(value); if (!value) void speech.stop(); }} /></View><View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}><Label size={13} style={{ flex: 1 }}>Obstacle alerts</Label><Switch accessibilityLabel="Obstacle alerts" disabled={busy || session?.status === 'closed'} value={alerts} trackColor={{ false: colors.trackOff, true: colors.primary }} onValueChange={value => { if (!value) void speech.stop(); void run(() => preferences(language, value)); }} /></View></View></Card>
    {!session ? <View style={ui.card}>
      <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}><SoraLogo size={36} /><View style={{ flex: 1, gap: 3 }}><Label bold size={16}>Start live assistance</Label><Label muted size={11}>Camera, voice & visual memory</Label></View></View><Text style={ui.copy}>Camera frames are analyzed and selected images and conversations are retained until the session expires. Voice uploads are processed without being retained.</Text>
      <View style={ui.row}><Switch accessibilityLabel="Consent to camera processing and retention" value={consent} trackColor={{ false: colors.trackOff, true: colors.primary }} onValueChange={setConsent} /><Text style={[ui.copy, { flex: 1 }]}>I consent to camera processing and visual memory storage.</Text></View>
      <Action variant="primary" title={busy ? 'Starting…' : 'Start a new session'} disabled={!consent || busy} onPress={() => void run(async () => {
        const created = await api.request<CaptureSession>('/sessions', 'POST', { consent: true, language, alerts_enabled: alerts });
        select(created); setActive(true); listSessions();
      })} />
      <Action title="Refresh sessions" onPress={listSessions} />
      {sessions.map(item => <Action key={item.id} title={`${new Date(item.created_at).toLocaleString()} · ${item.status}`} onPress={() => select(item)} />)}
    </View> : <>
      <Text style={ui.copy}>Session · {session.status} · expires {new Date(session.expires_at).toLocaleString()} · {connection}</Text>
      {session.status === 'active' && <><LiveCamera key={`${session.id}-${foreground}-${focused}-${active}`} sessionId={session.id} active={active && foreground && focused} />{active && foreground && focused && <StreamStatus sessionId={session.id} onUnavailable={fail} />}<Action title={active ? 'Pause assistance' : 'Resume assistance'} onPress={() => setActive(v => !v)} /></>}
      {active && <View style={ui.card}><Text style={ui.subtitle}>Live objects</Text><Text style={ui.copy}>{observation ? observation.detected_objects.length ? observation.detected_objects.map(object => `${object.label} (${Math.round(object.confidence * 100)}%)`).join(', ') : 'No supported objects detected. This does not mean the route is clear.' : 'Waiting for fresh detections…'}</Text>{observation && <Text style={ui.copy}>Server detection latency: {Math.round(observation.latency_ms)} ms</Text>}</View>}
      {frame && <View style={ui.card}><Text style={ui.subtitle}>Latest saved scene</Text><Text style={ui.copy}>{frame.caption || (['pending', 'processing'].includes(frame.enrichment_status || '') ? 'Frame saved. AI description is being prepared.' : 'Saved observations available below.')}</Text><Text style={ui.copy}>{frame.detected_objects.map(object => object.label).join(', ')}</Text>{!!frame.ocr_text && <Text style={ui.copy}>Text: {frame.ocr_text}</Text>}<Text style={ui.copy}>{new Date(frame.captured_at).toLocaleTimeString()}</Text>{frame.processing_warnings.map(w => <Text key={w} style={ui.error}>{w}</Text>)}</View>}
      <View style={ui.row}>{(['recent', 'memory', 'auto'] as const).map(value => <Action key={value} title={`${scope === value ? '✓ ' : ''}${value === 'recent' ? 'Current view' : value === 'memory' ? 'Memory' : 'Auto'}`} onPress={() => setScope(value)} />)}</View>
      <Card><View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}><Icon name="mic-outline" color={colors.accent} size={20} /><Label bold size={15}>Ask your companion</Label></View><VoiceWaveform commandsOnly={!active || !appPreferences.handsFreeQuestions} />
      {appPreferences.voiceCommands && <Text accessibilityLiveRegion="polite" style={ui.copy}>{voice.status}</Text>}
      <Field placeholder="Ask about your surroundings or memory" value={question} onChangeText={setQuestion} multiline maxLength={2000} />
      <Action title={busy ? 'Thinking…' : 'Ask Sora'} disabled={busy || !question.trim()} onPress={() => void run(ask)} />
      {foreground && focused && <VoiceQuestion key={session.id} sessionId={session.id} language={language} scope={scope} disabled={busy} onAnswer={answer => receiveAnswer(answer, true)} onError={setError} />}
      <Action title="Stop speaking" onPress={() => void speech.stop()} />
      </Card>
      <Label bold size={16}>Conversation</Label>
      {answers.length === 0 && <Text style={ui.copy}>Your conversation will appear here.</Text>}
      {answers.map(answer => <AnswerCard key={answer.id} answer={answer} onError={setError} />)}
      {session.status === 'active' && <Action title="End capture and keep memory" disabled={busy} onPress={() => void run(async () => { setActive(false); setSession(await api.request<CaptureSession>(`/sessions/${session.id}/close`, 'POST')); listSessions(); })} />}
      <Action title="Choose another session" disabled={busy} onPress={() => { select(null); listSessions(); }} />
    </>}
  </Page>;
}

import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, ScrollView, View } from 'react-native';
import { Image } from 'expo-image';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useHandsFreeQuestions } from '@/providers/voice-commands';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import { speech } from '@/lib/speech';
import { connectLive } from '@/lib/live';
import type { Answer, CaptureSession, Frame, Language } from '@/lib/api';
import { cameraFeedback } from '@/lib/camera-feedback';
import { AuthScreen } from './auth-screen';
import { ScreenIntro } from './brand';
import { Card, Icon, Label, Page, Tap } from './sora-ui';
const descriptionQuestion = 'Describe the captured scene in clear, concise language.';
export function CaptureResult({ text = false }: { text?: boolean }) {
  const { tokens } = useAuth(); return tokens ? <Result text={text} /> : <AuthScreen />;
}
function Result({ text }: { text: boolean }) {
  const { sessionId, frameId, answerId } = useLocalSearchParams<{ sessionId?: string; frameId?: string; answerId?: string }>();
  const { api } = useAuth(); const { colors, preferences } = usePreferences();
  const [frame, setFrame] = useState<Frame | null>(null); const [headers, setHeaders] = useState<Record<string, string>>();
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [answer, setAnswer] = useState(''); const [playing, setPlaying] = useState(false);
  const [attempt, setAttempt] = useState(0); const [focused, setFocused] = useState(true);
  const [language, setLanguage] = useState<Language>('en');
  const [uncertain, setUncertain] = useState(false); const [warnings, setWarnings] = useState<string[]>([]);
  const spoken = useRef('');
  const pendingDescription = useRef<number | null>(null);
  useFocusEffect(useCallback(() => { setFocused(true); return () => { setFocused(false); void speech.stop(); setPlaying(false); }; }, []));
  useEffect(() => speech.registerInterruptor(() => setPlaying(false)), []);
  useEffect(() => { const subscription = AppState.addEventListener('change', state => { if (state !== 'active') { void speech.stop(); setPlaying(false); } }); return () => subscription.remove(); }, []);
  useEffect(() => {
    if (!focused || text || !sessionId || !frameId) return;
    let cancelled = false;
    function receive(value: Answer) {
      if (cancelled || value.question !== descriptionQuestion || !value.evidence_frame_ids.includes(frameId!)) return;
      if (pendingDescription.current && Date.parse(value.created_at) < pendingDescription.current - 1000) return;
      setAnswer(value.answer); setUncertain(value.uncertain); setWarnings(value.processing_warnings);
      pendingDescription.current = null; setBusy(false); setError('');
    }
    // Reuse session events so a slow local model can still deliver the answer
    // after the shared HTTP client's bounded request has timed out.
    const live = connectLive(api, `/sessions/${sessionId}/events`, event => {
      if (event.question) receive(event.question);
      if (event.type === 'ready') void api.request<Answer[]>(`/sessions/${sessionId}/questions?limit=20`).then(values => { const latest = values.find(value => value.question === descriptionQuestion && value.evidence_frame_ids.includes(frameId!)); if (latest) receive(latest); }).catch(() => {});
    }, () => {});
    return () => { cancelled = true; live.close(); };
  }, [api, sessionId, frameId, focused, text]);
  useEffect(() => {
    if (!focused || !sessionId || !frameId) return;
    let cancelled = false; let timer: ReturnType<typeof setTimeout>; let polls = 0; let sessionLanguage: Language | undefined; let answerLoaded = false;
    async function load() {
      try {
        const token = await api.token();
        if (!sessionLanguage) sessionLanguage = (await api.request<CaptureSession>(`/sessions/${sessionId}`)).language;
        const value = await api.request<Frame>(`/sessions/${sessionId}/frames/${frameId}`);
        if (cancelled) return;
        if (answerId && !answerLoaded && !text) {
          const result = await api.request<Answer>(`/sessions/${sessionId}/questions/${answerId}`);
          if (cancelled) return;
          if (!result.evidence_frame_ids.includes(frameId!)) throw new Error('This description does not reference the selected image.');
          setAnswer(result.answer); setUncertain(result.uncertain); setWarnings(result.processing_warnings); answerLoaded = true;
        }
        setHeaders({ Authorization: `Bearer ${token}` }); setLanguage(sessionLanguage); setFrame(value); setError('');
        if (text) timer = setTimeout(() => void load(), 5000);
        else if (['pending', 'processing'].includes(value.enrichment_status || '') && ++polls < 90) timer = setTimeout(() => void load(), 2000);
        else if (['pending', 'processing'].includes(value.enrichment_status || '')) setError('Processing is taking longer than expected. Tap refresh to check again.');
      } catch (e) { if (!cancelled) setError(e instanceof Error ? e.message : 'Unable to load this image.'); }
    }
    void load(); return () => { cancelled = true; clearTimeout(timer); };
  }, [api, sessionId, frameId, answerId, attempt, focused, text]);
  const processing = frame && !answer && ['pending', 'processing'].includes(frame.enrichment_status || '');
  const content = text ? frame?.ocr_text : answer || frame?.caption;
  const resultCopy = content || (error && !frame ? 'Refresh or capture another image to continue.' : processing ? 'Your image is being analyzed.' : frame ? text ? 'No readable text detected. Try a closer, well-lit image.' : 'No scene description available. Try describing again.' : 'Loading your result…');
  const viewTip = !text && frame ? cameraFeedback(uncertain || frame.processing_warnings.includes('scene_uncertain'), content || '', [...warnings, ...frame.processing_warnings]) : null;
  const spokenContent = content && viewTip && language === 'en' ? `${content} ${viewTip}` : content;
  useEffect(() => {
    if (!spokenContent || !focused) return;
    speech.rememberAnswer(spokenContent, language);
    if (!preferences.speak || spoken.current === spokenContent) return;
    spoken.current = spokenContent; void speech.answer(spokenContent, language);
  }, [spokenContent, preferences.speak, focused, language]);
  useHandsFreeQuestions(async question => {
    if (!sessionId || !frame) throw new Error('Please wait for this image to load, then ask again.');
    if (busy) throw new Error('Please wait for the current description to finish, then ask again.');
    setBusy(true); setError('');
    try {
      const reply = await api.request<Answer>(`/sessions/${sessionId}/questions`, 'POST', { question, scope: 'memory', since: frame.captured_at, until: frame.captured_at, language });
      // The global voice listener reads this reply once, even with automatic speech enabled.
      spoken.current = reply.answer;
      setAnswer(reply.answer); setUncertain(reply.uncertain); setWarnings(reply.processing_warnings);
      return reply;
    } finally { setBusy(false); }
  }, `${sessionId}:${frameId}`);
  async function play() {
    if (playing) { await speech.stop(); setPlaying(false); return; }
    if (spokenContent) { speech.rememberAnswer(spokenContent, language); await speech.answer(spokenContent, language, () => setPlaying(false)); setPlaying(true); }
  }
  function retake() { router.replace({ pathname: '/camera', params: { mode: text ? 'text' : 'scene', sessionId } }); }
  async function describe() {
    if (!sessionId || !frame) return;
    pendingDescription.current = Date.now();
    setBusy(true); setError('');
    try {
      const value = await api.request<Answer>(`/sessions/${sessionId}/questions`, 'POST', { question: descriptionQuestion, scope: 'memory', since: frame.captured_at, until: frame.captured_at, language });
      setAnswer(value.answer);
      setUncertain(value.uncertain); setWarnings(value.processing_warnings);
      pendingDescription.current = null;
    } catch (e) { if (pendingDescription.current !== null) setError(e instanceof Error ? e.message : 'Description unavailable. Please try again.'); }
    finally { setBusy(false); }
  }
  return <Page title={text ? 'Read Text' : 'Scene Description'}>
    {!sessionId || !frameId ? <Card><Label>No captured image selected.</Label><Tap label="Open camera" onPress={retake}><Label>Open camera →</Label></Tap></Card> : <>
      <ScreenIntro eyebrow={text ? 'Text to speech' : 'Scene insight'} title={text ? 'Words, made clear.' : 'A closer look.'} subtitle={frame ? new Date(frame.captured_at).toLocaleString() : 'Your captured moment'} />
      <View style={{ height: 226, borderRadius: 18, overflow: 'hidden', backgroundColor: colors.elevated, borderWidth: 1, borderColor: colors.border, boxShadow: colors.cardShadow, marginTop: 2 }}>
        {frame && headers ? <Image source={{ uri: api.url(`/sessions/${sessionId}/frames/${frameId}/image`), headers }} style={{ flex: 1 }} contentFit="cover" cachePolicy="none" accessibilityLabel={frame.caption || 'Captured image'} onError={() => setError('Image unavailable. Refresh to renew access.')} /> : error ? <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 }}><Icon name="image-outline" /><Label muted>Image unavailable</Label></View> : <ActivityIndicator style={{ flex: 1 }} color={colors.primary} accessibilityLabel="Loading captured image" />}
      </View>
      <Card style={{ gap: 12 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}><Icon name={text ? 'scan-outline' : 'sparkles'} size={22} /><Label bold size={13}>{!frame ? error ? 'Result unavailable' : 'Loading image…' : processing ? 'Processing image…' : text ? frame.ocr_text ? 'Text Detected' : 'No Text Detected' : 'Scene Detected'}</Label></View>
        {processing && <ActivityIndicator color={colors.primary} accessibilityLabel="AI processing" />}
        {text ? <View style={{ borderRadius: 14, padding: 16, backgroundColor: colors.elevated }}><ScrollView nestedScrollEnabled showsVerticalScrollIndicator={false} style={{ maxHeight: 260 }}><Label bold size={20} selectable style={{ textAlign: 'center' }}>{resultCopy}</Label></ScrollView></View> : <Label bold size={22} selectable>{resultCopy}</Label>}
      </Card>
      {viewTip && <Card tone="accent" style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}><Icon name="camera-outline" size={20} /><Label accessibilityLiveRegion="polite" size={13} style={{ flex: 1 }}>{viewTip}</Label></Card>}
      {!!content && <Tap label={playing ? 'Stop audio' : text ? 'Read Aloud' : 'Play Description'} onPress={() => void play()}><Card tone="accent" style={{ flexDirection: 'row', alignItems: 'center', padding: 12, gap: 14 }}><View style={{ width: 46, height: 46, borderRadius: 23, backgroundColor: colors.primary, boxShadow: colors.primaryShadow, alignItems: 'center', justifyContent: 'center' }}><Icon name={playing ? 'stop' : 'play'} color={colors.onPrimary} size={23} /></View><Label bold size={13} style={{ flex: 1 }}>{playing ? 'Stop audio' : text ? 'Read Aloud' : 'Play Description'}</Label><Icon name="volume-high-outline" size={19} color={colors.muted} /></Card></Tap>}
      {!!error && <Card><Label accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Label><Tap label="Refresh result" onPress={() => setAttempt(v => v + 1)}><Label bold>Refresh →</Label></Tap></Card>}
      {frame?.processing_warnings.map(warning => <Label key={warning} accessibilityRole="alert" style={{ color: colors.danger }}>{warning}</Label>)}
      {warnings.filter(warning => !frame?.processing_warnings.includes(warning)).map(warning => <Label key={warning} accessibilityRole="alert" style={{ color: colors.danger }}>{warning}</Label>)}
      <View style={{ flexDirection: 'row', gap: 16 }}><Tap label={text ? 'Scan Another Text' : 'Retake'} onPress={retake} style={{ flex: 1 }}><Card tone="quiet" style={{ minHeight: text ? 80 : 112, alignItems: 'center', justifyContent: 'center', ...(text ? { flexDirection: 'row' } : {}) }}><Icon name={text ? 'scan-outline' : 'camera-outline'} color={text ? colors.primary : colors.text} size={29} /><Label bold size={14}>{text ? 'Scan Another Text' : 'Retake'}</Label></Card></Tap>{!text && <Tap label="Describe Again" disabled={busy || !frame} onPress={() => void describe()} style={{ flex: 1 }}><Card tone="quiet" style={{ minHeight: 112, alignItems: 'center', justifyContent: 'center' }}><Icon name="sync-outline" size={29} /><Label bold size={14} style={{ textAlign: 'center' }}>{busy ? 'Describing…' : 'Describe\nAgain'}</Label></Card></Tap>}</View>
    </>}
  </Page>;
}

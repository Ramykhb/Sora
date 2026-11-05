import { useFullscreenTabBar } from '@/providers/tab-bar';
import { ScreenIntro, SoraHero } from '@/components/brand';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Platform, StyleSheet, Switch, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { NavigationBar } from 'expo-navigation-bar';
import { LinearGradient } from 'expo-linear-gradient';
import { useHandsFreeQuestions, useVoiceCommands, useVoiceStreamControls } from '@/providers/voice-commands';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import type { StreamCommand } from '@/lib/voice-commands';
import type { Answer, CaptureSession, Frame } from '@/lib/api';
import { speech } from '@/lib/speech';
import { AuthScreen } from '@/components/auth-screen';
import { VoiceWaveform } from '@/components/voice-waveform';
import { LiveCamera } from '@/components/live-camera';
import { Card, Icon, Label, Page, Primary, Tap } from '@/components/sora-ui';
export default function CameraScreen() { const { tokens } = useAuth(); return tokens ? <Capture /> : <AuthScreen />; }
function Capture() {
  const params = useLocalSearchParams<{ mode?: string; sessionId?: string; voiceStart?: string }>();
  const mode = params.mode === 'text' ? 'text' : params.mode === 'scene' ? 'scene' : 'live';
  const { api } = useAuth(); const { preferences, colors, update, dark } = usePreferences();
  const roundStyle = [cameraStyles.round, { backgroundColor: colors.cameraControl, borderColor: colors.heroEdge }];
  const controlColor = colors.cameraInk;
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const [session, setSession] = useState<CaptureSession | null>(null);
  const [consent, setConsent] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const voice = useVoiceCommands();
  const [voiceAnswer, setVoiceAnswer] = useState('');
  const [connected, setConnected] = useState(false);
  const [facing, setFacing] = useState<'back' | 'front'>('back');
  const [focused, setFocused] = useState(true); const [foreground, setForeground] = useState(AppState.currentState === 'active');
  useFullscreenTabBar(!!session);
  useFocusEffect(useCallback(() => { setFocused(true); return () => { setFocused(false); void speech.stop(); }; }, []));
  useEffect(() => { const sub = AppState.addEventListener('change', value => { setForeground(value === 'active'); }); return () => sub.remove(); }, []);
  useEffect(() => { if (!session) return; const timer = setTimeout(() => { setSession(null); setError('This session expired. Start a new session.'); }, Math.max(0, Date.parse(session.expires_at) - Date.now())); return () => clearTimeout(timer); }, [session]);
  const [streamPaused, setStreamPaused] = useState(false);
  const changingStream = useRef(false);
  const starting = useRef(false);
  const consumedVoiceStart = useRef<string | undefined>(undefined);
  const startCamera = useCallback(async (fromVoice = false) => {
    if (starting.current) return;
    if (session) {
      if (streamPaused) setStreamPaused(false);
      if (fromVoice) void speech.answer(streamPaused ? 'Resuming your stream.' : 'Your stream is already running.', 'en');
      return;
    }
    starting.current = true;
    setBusy(true); setError('');
    if (fromVoice) { setConsent(true); void speech.answer('Starting your stream.', 'en'); }
    try {
      const granted = permission?.granted ? permission : await requestPermission();
      if (!granted.granted) throw new Error('Camera access is required. Enable it in your device settings, then try again.');
      const previous = params.sessionId ? await api.request<CaptureSession>(`/sessions/${params.sessionId}`) : null;
      const created = previous?.status === 'active' ? previous : await api.request<CaptureSession>('/sessions', 'POST', { consent: true, language: 'en', alerts_enabled: false });
      setStreamPaused(false); setSession(created);
      if (preferences.guidance) void speech.answer('Point your camera at your surroundings. Say describe the scene, or ask a question about your surroundings.', 'en');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to start your stream. Please try again.';
      setError(message);
      if (fromVoice) void speech.answer(message, 'en');
    } finally { starting.current = false; setBusy(false); }
  }, [api, params.sessionId, permission, requestPermission, preferences.guidance, session, streamPaused]);
  useEffect(() => {
    if (!focused || !foreground || mode !== 'live' || !params.voiceStart || consumedVoiceStart.current === params.voiceStart) return;
    consumedVoiceStart.current = params.voiceStart;
    void startCamera(true);
  }, [focused, foreground, mode, params.voiceStart, startCamera]);
  useHandsFreeQuestions(async question => {
    if (!session || mode !== 'live') throw new Error('Say Hey Sora, start stream first. Then ask about your surroundings.');
    if (streamPaused) throw new Error('Your stream is paused. Say Hey Sora, resume stream first.');
    if (!connected) throw new Error('Your stream is still connecting. Please try your question again in a moment.');
    if (busy || starting.current) throw new Error('Please wait for the current request to finish, then ask again.');
    setBusy(true); setError('');
    try {
      const answer = await api.request<Answer>(`/sessions/${session.id}/questions`, 'POST', { question, scope: 'recent', language: session.language });
      setVoiceAnswer(answer.answer);
      return answer;
    } finally { setBusy(false); }
  }, `${session?.id}:${streamPaused}`);
  async function controlStream(command: StreamCommand) {
    if (changingStream.current || starting.current) throw new Error('Please wait for the stream to finish changing, then try again.');
    if (!session || mode !== 'live') throw new Error('There is no live stream open. Say Hey Sora, start stream first.');
    if (command === 'pause-stream') {
      setStreamPaused(true); setConnected(false);
      return streamPaused ? 'Your stream is already paused.' : 'Stream paused. Say Hey Sora, resume stream when you are ready.';
    }
    if (command === 'resume-stream') {
      if (session.status !== 'active') throw new Error('This stream has ended. Say Hey Sora, start stream to begin a new one.');
      setStreamPaused(false);
      if (!focused) router.navigate({ pathname: '/camera', params: { mode: 'live' } });
      return streamPaused || !focused ? 'Resuming your stream.' : 'Your stream is already running.';
    }
    changingStream.current = true;
    // Release the camera immediately, even if closing the server session is slow.
    setStreamPaused(true); setConnected(false); setError('');
    try {
      await api.request<CaptureSession>(`/sessions/${session.id}/close`, 'POST');
      setSession(null); setVoiceAnswer(''); setStreamPaused(false);
      return 'Stream stopped. Your saved moments are still available.';
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to end the session. Please try stop stream again.');
      throw error;
    } finally { changingStream.current = false; }
  }
  useVoiceStreamControls(controlStream, !!session && mode === 'live', streamPaused);
  async function controlFromButton(command: StreamCommand) {
    try { await speech.answer(await controlStream(command), 'en'); }
    catch (error) { await speech.answer(error instanceof Error ? error.message : 'Unable to control your stream.', 'en'); }
  }
  async function run(work: () => Promise<void>) { setBusy(true); setError(''); try { await work(); } catch (e) { setError(e instanceof Error ? e.message : 'Capture failed. Please try again.'); } finally { setBusy(false); } }
  function result(frame: Frame, answerId?: string) {
    router.push({ pathname: mode === 'text' ? '/read-text' : '/scene', params: { sessionId: frame.session_id, frameId: frame.id, ...(answerId ? { answerId } : {}) } });
  }
  async function upload(uri: string, mime = 'image/jpeg', name = 'capture.jpg', sessionId = session?.id) {
    if (!sessionId) return;
    const form = new FormData();
    if (Platform.OS === 'web') form.append('image', await (await fetch(uri)).blob(), name);
    else form.append('image', { uri, type: mime, name } as unknown as Blob);
    form.append('force', 'true');
    setUploading(true);
    let value: { frame?: Frame | null; reason?: string };
    try { value = await api.upload<{ frame?: Frame | null; reason?: string }>(`/sessions/${sessionId}/frames`, form); }
    finally { setUploading(false); }
    if (!value.frame) throw new Error(value.reason || 'This image could not be processed. Try another image.');
    result(value.frame);
  }
  async function capture() {
    if (!session) return;
    if (streamPaused) throw new Error('Resume your stream before capturing a scene.');
    if (mode === 'live') {
      // The existing current-view question path saves a fresh WebRTC snapshot
      // and returns its retained evidence IDs. Keep that capture policy on the server.
      const answer = await api.request<Answer>(`/sessions/${session.id}/questions`, 'POST', { question: 'Describe the current scene', scope: 'recent', language: session.language });
      if (!answer.evidence_frame_ids[0]) throw new Error(answer.answer || 'Waiting for a fresh scene. Keep the camera steady and try again.');
      const frame = await api.request<Frame>(`/sessions/${session.id}/frames/${answer.evidence_frame_ids[0]}`);
      result(frame, answer.id); return;
    }
    const picture = await camera.current?.takePictureAsync({ quality: 0.85 });
    if (!picture) throw new Error('Camera is not ready. Please try again.');
    await upload(picture.uri);
  }
  if (!session) return <Page title={mode === 'text' ? 'Read Text' : 'Live Assistance'}><View style={{ flex: 1, justifyContent: 'center', gap: 22 }}><View style={{ alignItems: 'center' }}><SoraHero size={180} /></View><ScreenIntro eyebrow={mode === 'text' ? 'Text to speech' : 'Camera & voice'} title={mode === 'text' ? 'Every word, out loud.' : 'Let’s see what’s around.'} /><Card><Label muted>Camera images are analyzed to describe scenes and read text. Selected images and conversations are stored until your session expires.</Label><View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}><Switch accessibilityLabel="Consent to camera processing and visual memory storage" value={consent} onValueChange={setConsent} trackColor={{ false: colors.trackOff, true: colors.primary }} /><Label size={13} style={{ flex: 1 }}>I consent to camera processing and visual memory storage.</Label></View></Card>{!!error && <Label accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Label>}<Primary title={busy ? uploading ? 'Processing image\u2026' : 'Starting\u2026' : 'Start camera'} disabled={!consent || busy} onPress={() => void startCamera()} /><Tap label="Choose image without camera" disabled={!consent || busy} onPress={() => void run(async () => {
    // Open the picker directly from the gesture; browser file pickers need user activation.
    const picked = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.85 });
    if (picked.canceled) return;
    const previous = params.sessionId ? await api.request<CaptureSession>(`/sessions/${params.sessionId}`) : null;
    const created = previous?.status === 'active' ? previous : await api.request<CaptureSession>('/sessions', 'POST', { consent: true, language: 'en', alerts_enabled: false });
    const asset = picked.assets[0];
    await upload(asset.uri, asset.mimeType || 'image/jpeg', asset.fileName || 'gallery.jpg', created.id);
  })} style={{ alignItems: 'center', justifyContent: 'center' }}><Label bold>Choose from gallery</Label></Tap></View></Page>;
  return <View style={{ flex: 1, backgroundColor: colors.background }}>{focused && <><StatusBar style="light" /><NavigationBar style={dark ? 'light' : 'dark'} /></>}
    {focused && foreground && (mode === 'live' ? <LiveCamera sessionId={session.id} active={!streamPaused} fullscreen facing={facing} onConnectionChange={setConnected} /> : <CameraView ref={camera} style={StyleSheet.absoluteFill} facing={facing} />)}
    <SafeAreaView style={{ flex: 1, justifyContent: 'space-between' }} pointerEvents="box-none">
      <View style={{ flexDirection: 'row', paddingHorizontal: 18, paddingTop: 12, gap: 12, alignItems: 'center' }}><Tap label="Back to home" onPress={() => router.canGoBack() ? router.back() : router.replace('/')} style={roundStyle}><Icon name="chevron-back" color={controlColor} /></Tap><View style={{ flex: 1, alignItems: 'center' }}><View style={{ backgroundColor: colors.cameraControl, borderColor: colors.heroEdge, borderWidth: 1, borderRadius: 30, padding: 12, flexDirection: 'row', gap: 8, alignItems: 'center' }}><View style={{ width: 9, height: 9, borderRadius: 5, backgroundColor: mode !== 'live' || connected ? colors.success : colors.primary }} /><Label bold size={12} style={{ color: controlColor }}>{mode === 'live' ? streamPaused ? 'Stream paused' : connected ? 'Live Assistance' : 'Connecting...' : mode === 'text' ? 'Read Text' : 'Describe Scene'}</Label></View></View><Tap label={preferences.speak ? 'Mute descriptions' : 'Unmute descriptions'} onPress={() => { update({ speak: !preferences.speak }); void speech.stop(); }} style={roundStyle}><Icon name={preferences.speak ? 'volume-high-outline' : 'volume-mute-outline'} color={controlColor} size={23} /></Tap></View>
      <View pointerEvents="none" style={{ height: mode === 'live' ? '30%' : '40%', marginHorizontal: 40 }}>{[0, 1, 2, 3].map(index => <View key={index} style={{ position: 'absolute', width: 42, height: 42, borderColor: colors.cameraFrame, ...(index < 2 ? { top: 0, borderTopWidth: 4 } : { bottom: 0, borderBottomWidth: 4 }), ...(index % 2 === 0 ? { left: 0, borderLeftWidth: 4 } : { right: 0, borderRightWidth: 4 }), borderTopLeftRadius: index === 0 ? 16 : 0, borderTopRightRadius: index === 1 ? 16 : 0, borderBottomLeftRadius: index === 2 ? 16 : 0, borderBottomRightRadius: index === 3 ? 16 : 0 }} />)}</View>
      <View style={{ gap: 8 }}>
        <View style={{ gap: 13, backgroundColor: colors.cameraOverlay, borderColor: colors.heroEdge, borderTopWidth: 1, padding: 18, borderTopLeftRadius: 22, borderTopRightRadius: 22 }}>
        {mode === 'live' && <><Label bold size={14} style={{ color: controlColor, textAlign: 'center' }}>Sora · live companion</Label><VoiceWaveform commandsOnly={streamPaused || !preferences.handsFreeQuestions} /></>}
        {mode === 'live' && <View style={{ flexDirection: 'row', justifyContent: 'space-around', gap: 12 }}><Tap label={streamPaused ? 'Resume stream' : 'Pause stream'} onPress={() => void controlFromButton(streamPaused ? 'resume-stream' : 'pause-stream')} style={{ alignItems: 'center', justifyContent: 'center' }}><Label bold style={{ color: controlColor }}>{streamPaused ? 'Resume stream' : 'Pause stream'}</Label></Tap><Tap label="Stop stream" onPress={() => void controlFromButton('stop-stream')} style={{ alignItems: 'center', justifyContent: 'center' }}><Label bold style={{ color: colors.danger }}>Stop stream</Label></Tap></View>}
        {!!error && <Label accessibilityRole="alert" style={{ color: colors.danger, backgroundColor: colors.surface, padding: 12, borderRadius: 12 }}>{error}</Label>}
        {preferences.voiceCommands && <Label style={{ color: controlColor, textAlign: 'center' }} size={12}>{voice.status}</Label>}
        {!!voiceAnswer && <Label style={{ color: controlColor }} size={14}>{voiceAnswer}</Label>}
        {busy && <Label accessibilityLiveRegion="polite" style={{ color: controlColor, textAlign: 'center' }}>Processing your request…</Label>}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Tap label="Choose image from gallery" disabled={busy} onPress={() => void run(async () => { const picked = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.85 }); if (!picked.canceled) await upload(picked.assets[0].uri, picked.assets[0].mimeType || 'image/jpeg', picked.assets[0].fileName || 'gallery.jpg'); })} style={roundStyle}><Icon name="image-outline" color={dark ? controlColor : colors.primary} size={29} /></Tap>
          <Tap label={mode === 'live' ? 'Capture and describe current scene' : 'Capture image'} disabled={busy || streamPaused} onPress={() => void run(capture)} style={{ width: 86, height: 86, borderRadius: 43, borderWidth: 5, borderColor: colors.cameraFrame, padding: 4, boxShadow: colors.primaryShadow }}><LinearGradient colors={colors.buttonGradient} style={{ flex: 1, borderRadius: 40 }} /></Tap>
          <Tap label="Switch camera" disabled={busy} onPress={() => setFacing(value => value === 'back' ? 'front' : 'back')} style={roundStyle}><Icon name="camera-reverse-outline" color={controlColor} size={30} /></Tap>
        </View>
        </View>
      </View>
    </SafeAreaView>
  </View>;
}
const cameraStyles = StyleSheet.create({ round: { width: 54, height: 54, borderRadius: 27, borderWidth: 1, alignItems: 'center', justifyContent: 'center' } });

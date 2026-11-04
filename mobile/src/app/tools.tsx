import { useCallback, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useVoiceCommands } from '@/providers/voice-commands';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import type { CaptureSession, Frame } from '@/lib/api';
import { AuthScreen } from '@/components/auth-screen';
import { Welcome } from '@/components/welcome';
import { BottomNav, Card, Icon, Label, Page, Tap, styles } from '@/components/sora-ui';

function activityTime(timestamp: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(timestamp)) / 60000));
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} hr ago`;
  return new Date(timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
export default function Tools() {
  const { preferences } = usePreferences(); const { tokens } = useAuth();
  if (!preferences.onboarded) return <Welcome />;
  return tokens ? <Dashboard /> : <AuthScreen />;
}
function Dashboard() {
  const { api } = useAuth(); const { colors, preferences } = usePreferences();
  const voice = useVoiceCommands();
  const [sessions, setSessions] = useState<{ session: CaptureSession; frame?: Frame }[]>([]); const [error, setError] = useState('');
  const [loading, setLoading] = useState(true); const [refresh, setRefresh] = useState(0);
  useFocusEffect(useCallback(() => {
    let cancelled = false; setLoading(true); if (refresh > 0) setError('');
    void api.request<CaptureSession[]>('/sessions?limit=2').then(async values => Promise.all(values.map(async session => ({ session, frame: (await api.request<Frame[]>(`/sessions/${session.id}/frames?limit=1`))[0] })))).then(value => { if (!cancelled) { setSessions(value); setError(''); } }).catch(e => { if (!cancelled) setError(e.message); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, refresh]));
  const hour = new Date().getHours();
  return <Page footer={<BottomNav />}>
    <View style={[styles.row, { paddingHorizontal: 6, marginTop: 16, marginBottom: 6 }]}><View style={{ flex: 1, gap: 5 }}><Label bold size={23}>Good {hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'}!</Label><Label muted size={13}>How can I assist you today?</Label></View><Tap label="Your profile and preferences" onPress={() => router.push('/settings')} style={{ alignItems: 'center', justifyContent: 'center', borderRadius: 24, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, boxShadow: colors.quietShadow }}><Icon name="person-outline" color={colors.muted} size={22} /></Tap></View>
    <Tap label="Get assistance in real time" onPress={() => router.push('/camera')} style={{ borderRadius: 24, boxShadow: colors.primaryShadow }}>
      <LinearGradient colors={colors.gradient} locations={[0, 0.56, 1]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ padding: 24, minHeight: 154, borderRadius: 24, borderWidth: 1, borderColor: colors.heroEdge, justifyContent: 'center', gap: 12, overflow: 'hidden' }}>
        <LinearGradient pointerEvents="none" colors={[colors.heroSheen, '#FFFFFF00']} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0 }} />
        <LinearGradient pointerEvents="none" colors={[colors.heroEdge, colors.heroSheen, '#FFFFFF00']} start={{ x: 0, y: 0.5 }} end={{ x: 1, y: 0.5 }} style={{ position: 'absolute', width: 220, height: 90, right: -55, bottom: -42, borderRadius: 75, transform: [{ rotate: '-25deg' }] }} />
        <Icon name="camera-outline" color={colors.heroText} size={32} />
        <View style={styles.row}><Label bold size={20} style={{ color: colors.heroText, flex: 1 }}>Get assistance{'\n'}in real time</Label><View style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 22, backgroundColor: colors.heroArrow, borderWidth: 1, borderColor: colors.heroEdge, boxShadow: colors.quietShadow }}><Icon name="chevron-forward" color={colors.heroArrowInk} size={24} /></View></View>
      </LinearGradient>
    </Tap>
    <View style={{ flexDirection: 'row', gap: 14 }}>{([{ title: 'Describe\nScene', mode: 'scene', icon: 'camera-outline' }, { title: 'Read\nText', mode: 'text', icon: 'reader-outline' }] as const).map(item => <Tap key={item.mode} label={item.title.replace('\n', ' ')} onPress={() => router.push({ pathname: '/camera', params: { mode: item.mode } })} style={{ flex: 1 }}><Card style={{ minHeight: 132, alignItems: 'center', justifyContent: 'center', gap: 10 }}><Icon name={item.icon} size={32} /><Label bold size={16} style={{ textAlign: 'center' }}>{item.title}</Label></Card></Tap>)}</View>
    <Card tone="quiet" style={{ padding: 16, gap: 4 }}><Tap label="View all recent activity" onPress={() => router.push('/explore')} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><Label bold size={14}>Recent Activity</Label><Icon name="chevron-forward" size={20} color={colors.muted} /></Tap>
      {loading && <ActivityIndicator color={colors.primary} accessibilityLabel="Loading recent activity" />}
      {!!error && <><Label accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Label><Tap label="Retry recent activity" onPress={() => setRefresh(value => value + 1)}><Label bold>Try again →</Label></Tap></>}
      {!loading && !sessions.length && !error && <Label muted size={13} style={{ paddingBottom: 6 }}>No activity yet. Capture your first scene to get started.</Label>}
      {sessions.map(({ session: item, frame }) => <Tap key={item.id} label={`Open session from ${new Date(item.created_at).toLocaleString()}`} onPress={() => frame ? router.push({ pathname: frame.ocr_text ? '/read-text' : '/scene', params: { sessionId: item.id, frameId: frame.id } }) : router.push('/explore')} style={{ flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 10, borderTopWidth: 1, borderColor: colors.separator }}><Icon name={frame?.ocr_text ? 'reader-outline' : 'image-outline'} size={21} /><View style={{ flex: 1, gap: 2 }}><Label bold size={12}>{frame?.ocr_text ? 'Read text' : frame?.caption ? 'Scene description' : 'Live assistance'}</Label><Label muted size={11}>{activityTime(frame?.captured_at || item.created_at)}</Label></View></Tap>)}
    </Card>
    {preferences.voiceCommands && <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9, paddingHorizontal: 7 }}><Icon name="mic-outline" size={17} color={colors.muted} /><Label accessibilityLiveRegion="polite" muted size={11} style={{ flex: 1 }}>{voice.status}</Label></View>}
    <Tap label="Open full assistant, voice questions and live detection" onPress={() => router.push('/assistant')} style={{ alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 9 }}><Icon name="mic-outline" color={colors.muted} size={17} /><Label muted size={12}>Ask with your voice</Label></Tap>
  </Page>;
}

import { ScreenIntro } from '@/components/brand';
import { PreferenceControls } from '@/components/preference-controls';
import { SavedDestinationsSettings } from '@/components/saved-destinations-settings';
import { BottomNav, Icon, Label, Page, Tap } from '@/components/sora-ui';
import { useCallback, useState } from 'react';
import { Alert, Platform, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { useAuth } from '@/providers/auth';
import type { User } from '@/lib/api';
import { Action, Field, useUI } from '@/components/controls';

type LoginSession = { id: string; created_at: string; expires_at: string; is_current: boolean };
export default function SettingsScreen() {
  const { tokens } = useAuth();
  return <Settings key={tokens?.user.id || 'device'} />;
}
function Settings() {
  const ui = useUI();
  const { api, tokens } = useAuth();
  const [account, setAccount] = useState(false);
  const [name, setName] = useState(tokens?.user.display_name || '');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [sessions, setSessions] = useState<LoginSession[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  async function run(work: () => Promise<void>) {
    setBusy(true); setMessage('');
    try { await work(); } catch (e) { setMessage(e instanceof Error ? e.message : 'Request failed'); } finally { setBusy(false); }
  }
  useFocusEffect(useCallback(() => {
    if (!tokens) return;
    let cancelled = false;
    void Promise.all([api.request<LoginSession[]>('/auth/sessions'), api.request<Record<string, unknown>>('/metrics')]).then(([logins, values]) => { if (!cancelled) { setSessions(logins); setMetrics(values); } }).catch(e => { if (!cancelled) setMessage(e.message); });
    return () => { cancelled = true; };
  }, [api, tokens]));
  async function logout(all = false) { await api.request(all ? '/auth/logout-all' : '/auth/logout', 'POST'); await api.setTokens(null); router.replace('/'); }
  function deleteAccount() {
    const work = async () => { await api.request('/auth/me', 'DELETE', { password }); await api.setTokens(null); router.replace('/'); };
    if (Platform.OS === 'web') { if (window.confirm('Permanently delete your account and all retained data?')) void run(work); }
    else Alert.alert('Delete account?', 'This permanently removes your account and retained data.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: () => void run(work) }]);
  }
  return <Page title="Settings" footer={<BottomNav active="Settings" />}>
    <ScreenIntro eyebrow="Make it yours" title="Your Sora, your way." subtitle="Tune the experience to what works for you." />
    <SavedDestinationsSettings /><PreferenceControls /><Tap label={account ? 'Hide account settings' : 'Account, security & retained data'} onPress={() => tokens ? setAccount(value => !value) : router.push('/assistant')} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 12 }}><Label muted size={13}>Account, security & retained data</Label><Icon name={account ? 'chevron-down' : 'chevron-forward'} size={20} /></Tap>{account && tokens && <><Text style={ui.copy}>{tokens?.user.email} · {tokens?.user.email_verified ? 'Verified' : 'Unverified'}</Text>
    {!!message && <Text accessibilityLiveRegion="polite" style={ui.copy}>{message}</Text>}
    <Field placeholder="Display name" value={name} onChangeText={setName} maxLength={100} />
    <Action variant="primary" title="Save profile" disabled={busy || !name.trim()} onPress={() => void run(async () => {
      const user = await api.request<User>('/auth/me', 'PATCH', { display_name: name.trim() });
      if (api.tokens) await api.setTokens({ ...api.tokens, user }); setMessage('Profile saved.');
    })} />
    <View style={ui.card}><Text style={ui.subtitle}>Change password</Text><Field placeholder="Current password" value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" /><Field placeholder="New password (at least 12 characters)" value={newPassword} onChangeText={setNewPassword} secureTextEntry autoCapitalize="none" />
      <Action title="Change password and sign out" disabled={busy || !password || newPassword.length < 12} onPress={() => void run(async () => { await api.request('/auth/change-password', 'POST', { current_password: password, new_password: newPassword }); await api.setTokens(null); router.replace('/'); })} /></View>
    <Text style={ui.subtitle}>Signed-in devices</Text>{sessions.map(session => <View key={session.id} style={ui.card}><Text style={ui.copy}>{session.is_current ? 'This device' : 'Another device'} · {new Date(session.created_at).toLocaleString()}</Text><Action title="Revoke sign-in" disabled={busy} onPress={() => void run(async () => { await api.request(`/auth/sessions/${session.id}`, 'DELETE'); if (session.is_current) { await api.setTokens(null); router.replace('/'); } else setSessions(previous => previous.filter(value => value.id !== session.id)); })} /></View>)}
    {metrics && <View style={ui.card}><Text style={ui.subtitle}>Your retained data</Text>{Object.entries(metrics).filter(([, value]) => typeof value === 'number').map(([key, value]) => <Text key={key} style={ui.copy}>{key.replaceAll('_', ' ')}: {String(value)}</Text>)}</View>}
    <Action title="Sign out" disabled={busy} onPress={() => void run(() => logout())} /><Action title="Sign out all devices" disabled={busy} onPress={() => void run(() => logout(true))} />
    <Text style={ui.copy}>To delete your account, enter your current password above.</Text><Action variant="danger" title="Delete account and retained data" disabled={busy || !password} onPress={deleteAccount} />
  </>}</Page>;
}

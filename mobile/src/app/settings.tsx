import { useCallback, useState } from 'react';
import { Alert, Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useFocusEffect } from 'expo-router';
import { useAuth } from '@/providers/auth';
import type { User } from '@/lib/api';
import { AuthScreen } from '@/components/auth-screen';
import { Action, Field, ui } from '@/components/controls';

type LoginSession = { id: string; created_at: string; expires_at: string; is_current: boolean };
export default function SettingsScreen() {
  const { tokens } = useAuth();
  return tokens ? <Settings key={tokens.user.id} /> : <AuthScreen />;
}
function Settings() {
  const { api, tokens } = useAuth();
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
    let cancelled = false;
    void Promise.all([api.request<LoginSession[]>('/auth/sessions'), api.request<Record<string, unknown>>('/metrics')]).then(([logins, values]) => { if (!cancelled) { setSessions(logins); setMetrics(values); } }).catch(e => { if (!cancelled) setMessage(e.message); });
    return () => { cancelled = true; };
  }, [api]));
  async function logout(all = false) { await api.request(all ? '/auth/logout-all' : '/auth/logout', 'POST'); await api.setTokens(null); router.replace('/'); }
  function deleteAccount() {
    const work = async () => { await api.request('/auth/me', 'DELETE', { password }); await api.setTokens(null); router.replace('/'); };
    if (Platform.OS === 'web') { if (window.confirm('Permanently delete your account and all retained data?')) void run(work); }
    else Alert.alert('Delete account?', 'This permanently removes your account and retained data.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: () => void run(work) }]);
  }
  return <SafeAreaView style={ui.screen}><ScrollView contentContainerStyle={ui.content} keyboardShouldPersistTaps="handled">
    <Action title="Back to Sora" onPress={() => router.replace('/')} /><Text style={ui.title}>Settings</Text><Text style={ui.copy}>{tokens?.user.email} · {tokens?.user.email_verified ? 'Verified' : 'Unverified'}</Text>
    {!!message && <Text accessibilityLiveRegion="polite" style={ui.copy}>{message}</Text>}
    <Field placeholder="Display name" value={name} onChangeText={setName} maxLength={100} />
    <Action title="Save profile" disabled={busy || !name.trim()} onPress={() => void run(async () => {
      const user = await api.request<User>('/auth/me', 'PATCH', { display_name: name.trim() });
      if (api.tokens) await api.setTokens({ ...api.tokens, user }); setMessage('Profile saved.');
    })} />
    <View style={ui.card}><Text style={ui.subtitle}>Change password</Text><Field placeholder="Current password" value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" /><Field placeholder="New password (at least 12 characters)" value={newPassword} onChangeText={setNewPassword} secureTextEntry autoCapitalize="none" />
      <Action title="Change password and sign out" disabled={busy || !password || newPassword.length < 12} onPress={() => void run(async () => { await api.request('/auth/change-password', 'POST', { current_password: password, new_password: newPassword }); await api.setTokens(null); router.replace('/'); })} /></View>
    <Text style={ui.subtitle}>Signed-in devices</Text>{sessions.map(session => <View key={session.id} style={ui.card}><Text style={ui.copy}>{session.is_current ? 'This device' : 'Another device'} · {new Date(session.created_at).toLocaleString()}</Text><Action title="Revoke sign-in" disabled={busy} onPress={() => void run(async () => { await api.request(`/auth/sessions/${session.id}`, 'DELETE'); if (session.is_current) { await api.setTokens(null); router.replace('/'); } else setSessions(previous => previous.filter(value => value.id !== session.id)); })} /></View>)}
    {metrics && <View style={ui.card}><Text style={ui.subtitle}>Your retained data</Text>{Object.entries(metrics).filter(([, value]) => typeof value === 'number').map(([key, value]) => <Text key={key} style={ui.copy}>{key.replaceAll('_', ' ')}: {String(value)}</Text>)}</View>}
    <Action title="Sign out" disabled={busy} onPress={() => void run(() => logout())} /><Action title="Sign out all devices" disabled={busy} onPress={() => void run(() => logout(true))} />
    <Text style={ui.copy}>To delete your account, enter your current password above.</Text><Action title="Delete account and retained data" disabled={busy || !password} onPress={deleteAccount} />
  </ScrollView></SafeAreaView>;
}

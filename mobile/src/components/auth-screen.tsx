import { useState } from 'react';
import { ActivityIndicator, Image, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import type { Tokens } from '@/lib/api';
import { Action, Field, useUI } from './controls';
import { Card, Icon, Label, Tap } from './sora-ui';
type AuthMode = 'login' | 'register' | 'recover' | 'reset' | 'verify';
const modeTitles: Record<AuthMode, string> = { login: 'Sign in', register: 'Create account', recover: 'Forgot password', reset: 'Use reset token', verify: 'Verify email' };
export function AuthScreen() {
  const ui = useUI();
  const { colors } = usePreferences();
  const { api, ready, error: restoreError, retry, serverUrl, setServerUrl } = useAuth();
  const [editingServer, setEditingServer] = useState(false);
  const [serverAddress, setServerAddress] = useState('');
  const [mode, setMode] = useState<AuthMode>('login');
  const [moreOptions, setMoreOptions] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  function chooseMode(value: AuthMode) { setMode(value); setMessage(''); setPassword(''); }
  const basicModes: AuthMode[] = mode === 'login' ? ['register', 'recover'] : mode === 'register' ? ['login', 'verify'] : mode === 'recover' ? ['login', 'reset'] : ['login'];
  async function submit() {
    setBusy(true); setMessage('');
    try {
      if (mode === 'recover') {
        await api.publicRequest('/auth/forgot-password', { email });
        setMessage('If eligible, you will receive a password reset email.');
      } else if (mode === 'reset' || mode === 'verify') {
        await api.publicRequest(`/auth/${mode === 'reset' ? 'reset-password' : 'verify-email'}`, { token, ...(mode === 'reset' ? { new_password: password } : {}) });
        setMode('login'); setPassword(''); setToken(''); setMessage('Done. You can now sign in.');
      } else {
        if (mode === 'register') {
          await api.publicRequest('/auth/register', { email, password, display_name: name });
          setMode('login'); setPassword(''); setMessage('Account created. Check your email if verification is required, then sign in.');
        } else await api.setTokens(await api.publicRequest<Tokens>('/auth/login', { email, password }));
      }
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Unable to sign in.'); }
    finally { setBusy(false); }
  }
  if (!ready) return <SafeAreaView style={ui.screen}><ActivityIndicator accessibilityLabel="Restoring sign-in" /></SafeAreaView>;
  return <SafeAreaView style={ui.screen}><ScrollView showsVerticalScrollIndicator={false} showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={ui.content}>
    <View style={{ alignItems: 'center', gap: 8, paddingTop: 22, paddingBottom: 18 }}><Tap label="Preferences" onPress={() => router.push('/settings')} style={{ position: 'absolute', top: 0, right: 0, alignItems: 'center', justifyContent: 'center' }}><Icon name="settings-outline" color={colors.muted} size={22} /></Tap><Image source={require('../../assets/images/sora-ribbon.png')} style={{ width: 90, height: 95 }} resizeMode="contain" accessibilityLabel="SORA ribbon logo" /><Text style={[ui.title, { letterSpacing: 9 }]}>SORA</Text><Text style={ui.copy}>See beyond.</Text></View>
    <Card style={{ gap: 16 }}>
    <Label accessibilityRole="header" bold size={20}>{mode === 'register' ? 'Create your account' : mode === 'login' ? 'Sign in to SORA' : mode === 'recover' ? 'Reset your password' : mode === 'reset' ? 'Choose a new password' : 'Verify your email'}</Label>
    {!!restoreError && <><Text style={ui.error}>{restoreError}</Text><Action title="Retry saved sign-in" onPress={retry} /></>}
    {mode === 'register' && <Field placeholder="Display name" value={name} onChangeText={setName} autoComplete="name" />}
    {['login', 'register', 'recover'].includes(mode) && <Field placeholder="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />}
    {['reset', 'verify'].includes(mode) && <Field placeholder="Token from your email link" value={token} onChangeText={setToken} autoCapitalize="none" />}
    {['login', 'register', 'reset'].includes(mode) && <Field placeholder={mode === 'login' ? 'Password' : 'Password (at least 12 characters)'} value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />}
    {!!message && <Text accessibilityLiveRegion="polite" style={ui.copy}>{message}</Text>}
    <Action variant="primary" title={busy ? 'Please wait…' : 'Continue'} disabled={busy} onPress={() => void submit()} />
    </Card>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8 }}>{basicModes.map(value => <Tap key={value} label={modeTitles[value]} disabled={busy} onPress={() => chooseMode(value)} style={{ justifyContent: 'center', paddingHorizontal: 4 }}><Label size={12} bold>{modeTitles[value]}</Label></Tap>)}</View>
    <Tap label="More sign-in options" expanded={moreOptions} onPress={() => setMoreOptions(value => !value)} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 }}><Label muted size={12}>More sign-in options</Label><Icon name={moreOptions ? 'chevron-up' : 'chevron-down'} size={16} color={colors.muted} /></Tap>
    {moreOptions && <Card tone="quiet" style={{ gap: 12 }}>
      <Label muted size={12}>Connection & email access</Label>
      <Text style={ui.copy}>Server: {serverUrl}</Text>
      <Action title={editingServer ? 'Cancel server change' : 'Change server'} disabled={busy} onPress={() => { setServerAddress(serverUrl); setEditingServer(value => !value); }} />
      {editingServer && <>
        <Text style={ui.copy}>Enter your backend address. For a server on your computer, use its Wi-Fi IP and port 8000.</Text>
        <Field placeholder="http://192.168.1.10:8000" value={serverAddress} onChangeText={setServerAddress} autoCapitalize="none" autoCorrect={false} keyboardType="url" />
        <Action title="Save server" disabled={busy} onPress={() => {
          setBusy(true); setMessage('');
          void setServerUrl(serverAddress).then(() => { setEditingServer(false); setMessage('Server saved. You can now sign in.'); }).catch(e => setMessage(e.message)).finally(() => setBusy(false));
        }} />
      </>}
      {(['reset', 'verify'] as const).filter(value => value !== mode && !basicModes.includes(value)).map(value => <Action key={value} title={modeTitles[value]} disabled={busy} onPress={() => chooseMode(value)} />)}
      <Action title="Resend verification email" disabled={busy || !email} onPress={() => { setBusy(true); void api.publicRequest('/auth/resend-verification', { email }).then(() => setMessage('If eligible, a verification email will be sent.')).catch(e => setMessage(e.message)).finally(() => setBusy(false)); }} />
    </Card>}
  </ScrollView></SafeAreaView>;
}

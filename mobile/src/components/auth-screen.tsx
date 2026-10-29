import { useState } from 'react';
import { ActivityIndicator, ScrollView, Text } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '@/providers/auth';
import type { Tokens } from '@/lib/api';
import { Action, Field, ui } from './controls';
export function AuthScreen() {
  const { api, ready, error: restoreError, retry } = useAuth();
  const [mode, setMode] = useState<'login' | 'register' | 'recover' | 'reset' | 'verify'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
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
  return <SafeAreaView style={ui.screen}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={ui.content}>
    <Text style={ui.title}>sora</Text><Text style={ui.subtitle}>Your everyday companion</Text>
    <Text style={ui.copy}>{mode === 'register' ? 'Create your account' : mode === 'login' ? 'Sign in to your visual memory' : mode === 'recover' ? 'Request a password reset' : mode === 'reset' ? 'Reset your password' : 'Verify your email'}</Text>
    {!!restoreError && <><Text style={ui.error}>{restoreError}</Text><Action title="Retry saved sign-in" onPress={retry} /></>}
    {mode === 'register' && <Field placeholder="Display name" value={name} onChangeText={setName} autoComplete="name" />}
    {['login', 'register', 'recover'].includes(mode) && <Field placeholder="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />}
    {['reset', 'verify'].includes(mode) && <Field placeholder="Token from your email link" value={token} onChangeText={setToken} autoCapitalize="none" />}
    {['login', 'register', 'reset'].includes(mode) && <Field placeholder={mode === 'login' ? 'Password' : 'Password (at least 12 characters)'} value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />}
    {!!message && <Text accessibilityLiveRegion="polite" style={ui.copy}>{message}</Text>}
    <Action title={busy ? 'Please wait…' : 'Continue'} disabled={busy} onPress={() => void submit()} />
    {(['login', 'register', 'recover', 'reset', 'verify'] as const).filter(v => v !== mode).map(v => <Action key={v} title={{ login: 'Sign in', register: 'Create account', recover: 'Forgot password', reset: 'Use reset token', verify: 'Verify email' }[v]} disabled={busy} onPress={() => { setMode(v); setMessage(''); setPassword(''); }} />)}
    <Action title="Resend verification email" disabled={busy || !email} onPress={() => { setBusy(true); void api.publicRequest('/auth/resend-verification', { email }).then(() => setMessage('If eligible, a verification email will be sent.')).catch(e => setMessage(e.message)).finally(() => setBusy(false)); }} />
  </ScrollView></SafeAreaView>;
}

import { useState } from 'react';
import { useAuth } from '../providers/Auth.jsx';
export default function AuthScreen() {
  const { api, ready, error, retry } = useAuth();
  const params = new URLSearchParams(location.search);
  const [mode, setMode] = useState(params.has('token') ? (location.pathname.includes('verify') ? 'verify' : 'reset') : 'login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [token, setToken] = useState(params.get('token') || '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      if (mode === 'login') api.setTokens(await api.publicRequest('/auth/login', { email, password }));
      else if (mode === 'register') {
        await api.publicRequest('/auth/register', { email, password, display_name: name });
        setMode('login'); setPassword(''); setMessage('Account created. Verify your email if required, then sign in.');
      } else if (mode === 'recover' || mode === 'resend') {
        await api.publicRequest(mode === 'recover' ? '/auth/forgot-password' : '/auth/resend-verification', { email });
        setMessage('If your account is eligible, an email will be sent.');
      } else {
        await api.publicRequest(mode === 'reset' ? '/auth/reset-password' : '/auth/verify-email', { token, ...(mode === 'reset' ? { new_password: password } : {}) });
        history.replaceState(null, '', `${location.pathname}#overview`);
        setMode('login'); setPassword(''); setToken(''); setMessage('Done. You can now sign in.');
      }
    } catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }
  if (!ready) return <div className="auth-shell"><div className="panel auth-card" role="status">Restoring sign-in…</div></div>;
  return <div className="auth-shell"><div className="panel auth-card">
    <a className="brand" href="#overview"><span className="brand-mark">✳</span>sora.</a><h1>{{ login: 'Welcome back.', register: 'Create an account.', recover: 'Reset your password.', reset: 'Choose a new password.', verify: 'Verify your email.', resend: 'Request verification.' }[mode]}</h1>
    <p>Sign in with the same account you use on mobile to see its camera stream and visual memory.</p>
    {error && <div className="notice error" role="alert">{error}<button className="button" onClick={retry}>Retry saved sign-in</button></div>}
    <form onSubmit={submit} className="form-stack">
      {mode === 'register' && <label>Display name<input value={name} onChange={e => setName(e.target.value)} autoComplete="name" required maxLength={100} /></label>}
      {['login', 'register', 'recover', 'resend'].includes(mode) && <label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" required /></label>}
      {['reset', 'verify'].includes(mode) && <label>Email token<input value={token} onChange={e => setToken(e.target.value)} required /></label>}
      {['login', 'register', 'reset'].includes(mode) && <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={mode === 'login' ? 1 : 12} maxLength={128} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required /></label>}
      {message && <div className="notice" role="status">{message}</div>}
      <button className="button primary" disabled={busy}>{busy ? 'Please wait…' : 'Continue'}</button>
    </form><div className="auth-links">{Object.entries({ login: 'Sign in', register: 'Create account', recover: 'Forgot password', reset: 'Use reset token', verify: 'Verify email', resend: 'Resend verification' }).filter(([value]) => value !== mode).map(([value, label]) => <button className="text-link" disabled={busy} key={value} onClick={() => { setMode(value); setPassword(''); setMessage(''); }}>{label}</button>)}</div>
  </div></div>;
}

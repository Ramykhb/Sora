import { useEffect, useState } from 'react';
import { Heading } from '../components/Shared.jsx';
import SpeechTools from '../components/SpeechTools.jsx';
import { useAuth } from '../providers/Auth.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
function AdminTools() {
  const { api } = useAuth();
  const { setError } = useDashboard();
  const [users, setUsers] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  async function load() { setUsers(await api.request('/auth/users?limit=200')); }
  async function run(operation) {
    setBusy(true);
    try { await operation(); } catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  return <section className="panel panel-body form-stack"><h2>Administrator operations</h2><p>These controls apply beyond your account and require an administrator role.</p><div className="action-row"><button className="button" disabled={busy} onClick={() => void run(load)}>Load users</button>{['cleanup', 'reconcile'].map(task => <button key={task} className="button" disabled={busy} onClick={() => { if (confirm(`Run ${task} maintenance?`)) void run(async () => setResult(await api.request(`/maintenance/${task}`, 'POST'))); }}>Run {task}</button>)}<button className="button" disabled={busy} onClick={() => void run(async () => setResult(await api.readiness()))}>Check dependencies</button></div>{result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    {users.map(user => <div className="setting" key={user.id}><div><strong>{user.display_name}</strong><p>{user.email} · {user.role} · {user.is_active ? 'active' : 'disabled'}</p></div><div className="action-row"><button className="button" disabled={busy} onClick={() => { if (confirm(`${user.is_active ? 'Disable' : 'Enable'} ${user.email}?`)) void run(async () => { await api.request(`/auth/users/${user.id}`, 'PATCH', { is_active: !user.is_active }); await load(); }); }}>{user.is_active ? 'Disable' : 'Enable'}</button><button className="button" disabled={busy} onClick={() => { if (confirm(`Change ${user.email} to ${user.role === 'admin' ? 'user' : 'admin'}?`)) void run(async () => { await api.request(`/auth/users/${user.id}`, 'PATCH', { role: user.role === 'admin' ? 'user' : 'admin' }); await load(); }); }}>Change role</button></div></div>)}
  </section>;
}
export default function Preferences() {
  const { api, tokens } = useAuth();
  const { session, selectedId, refreshSessions, refreshData, spoken, setSpoken, stopSpeaking, setError } = useDashboard();
  const [name, setName] = useState(tokens.user.display_name);
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [logins, setLogins] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => { let disposed = false; void api.request('/auth/sessions').then(rows => { if (!disposed) setLogins(rows); }).catch(e => { if (!disposed) setError(e.message); }); return () => { disposed = true; }; }, [api, setError]);
  async function run(work) {
    setBusy(true); setMessage(''); setError('');
    try { await work(); } catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  async function logout(all = false) { await api.request(all ? '/auth/logout-all' : '/auth/logout', 'POST'); stopSpeaking(); api.setTokens(null); }
  async function update(body) { await api.request(`/sessions/${selectedId}`, 'PATCH', body); await refreshSessions(); setMessage('Session preferences saved.'); }
  return <><Heading title="Make it feel like you." subtitle="Account security and preferences for your selected capture session." />
    {message && <div className="notice" role="status">{message}</div>}
    <div className="settings-grid"><section className="panel panel-body form-stack"><h2>Assistance</h2><label className="check-label"><input type="checkbox" checked={spoken} onChange={e => { setSpoken(e.target.checked); if (!e.target.checked) stopSpeaking(); }} />Automatically play new answers</label>
      <label>Session language<select value={session?.language || 'en'} disabled={!session || session.status !== 'active' || busy} onChange={e => void run(() => update({ language: e.target.value }))}><option value="en">English</option><option value="fr">Français</option><option value="ar">العربية</option></select></label>
      <label className="check-label"><input type="checkbox" checked={session?.alerts_enabled || false} disabled={!session || session.status !== 'active' || busy} onChange={e => void run(() => update({ alerts_enabled: e.target.checked }))} />Obstacle alerts for this session</label>
      <p>Retention is configured by the backend.{session && ` This session expires ${new Date(session.expires_at).toLocaleString()}.`}</p>
      <button className="button danger" disabled={!session || busy} onClick={() => { if (confirm('Permanently delete this session and its images, conversations and alerts?')) void run(async () => { await api.request(`/sessions/${selectedId}`, 'DELETE'); await refreshSessions(); }); }}>Delete selected session</button>
    </section><section className="panel panel-body form-stack"><h2>Your profile</h2><p>{tokens.user.email} · {tokens.user.email_verified ? 'Email verified' : 'Email unverified'}</p><label>Display name<input value={name} onChange={e => setName(e.target.value)} maxLength={100} /></label><button className="button" disabled={busy || !name.trim()} onClick={() => void run(async () => { const user = await api.request('/auth/me', 'PATCH', { display_name: name.trim() }); if (api.tokens) api.setTokens({ ...api.tokens, user }); setMessage('Profile saved.'); })}>Save profile</button><button className="button" disabled={busy} onClick={() => void run(async () => { await api.publicRequest('/auth/resend-verification', { email: tokens.user.email }); setMessage('If eligible, a verification email will be sent.'); })}>Resend verification</button></section>
    <section className="panel panel-body form-stack"><h2>Password & account</h2><label>Current password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label><label>New password<input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={newPassword} onChange={e => setNewPassword(e.target.value)} /></label><button className="button" disabled={busy || !password || newPassword.length < 12} onClick={() => void run(async () => { await api.request('/auth/change-password', 'POST', { current_password: password, new_password: newPassword }); api.setTokens(null); })}>Change password and sign out</button><button className="button danger" disabled={busy || !password} onClick={() => { if (confirm('Permanently delete your account and all retained data?')) void run(async () => { await api.request('/auth/me', 'DELETE', { password }); api.setTokens(null); }); }}>Delete account and data</button></section>
    <section className="panel panel-body form-stack"><h2>Signed-in devices</h2>{logins.map(login => <div className="setting" key={login.id}><div><strong>{login.is_current ? 'This browser' : 'Another device'}</strong><p>{new Date(login.created_at).toLocaleString()}</p></div><button className="button" disabled={busy} onClick={() => void run(async () => { await api.request(`/auth/sessions/${login.id}`, 'DELETE'); if (login.is_current) api.setTokens(null); else setLogins(previous => previous.filter(item => item.id !== login.id)); })}>Revoke</button></div>)}<div className="action-row"><button className="button" disabled={busy} onClick={() => void run(() => logout())}>Sign out</button><button className="button" disabled={busy} onClick={() => void run(() => logout(true))}>Sign out all devices</button></div></section></div>
    <SpeechTools />{tokens.user.role === 'admin' && <AdminTools />}
  </>;
}

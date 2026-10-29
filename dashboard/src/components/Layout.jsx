import Icon from './Icon.jsx';
import { pageTitles } from '../hooks/usePage.js';
import { useAuth } from '../providers/Auth.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
const navigation = [['overview', 'overview'], ['live', 'video'], ['frames', 'image'], ['questions', 'message'], ['settings', 'settings']];
export default function Layout({ page, onHelp, mainRef, children }) {
  const { tokens } = useAuth();
  const { sessions, selectedId, select, followLive, setFollowLive, connection, error, setError, mediaError, setMediaError, refreshSessions, loading } = useDashboard();
  const user = tokens.user;
  const initials = user.display_name.split(/\s+/).map(word => word[0]).slice(0, 2).join('').toUpperCase();
  return <>
    <a className="skip" href="#content" onClick={event => { event.preventDefault(); mainRef.current?.focus(); }}>Skip to content</a>
    <aside className="sidebar"><a className="brand" href="#overview" aria-label="Sora home"><span className="brand-mark">✳</span>sora<span className="brand-period">.</span></a><span className="workspace-label">VISUAL ASSISTANCE</span>
      <nav aria-label="Main navigation">{navigation.map(([id, name]) => <a key={id} href={`#${id}`} className={page === id ? 'active' : undefined} aria-current={page === id ? 'page' : undefined}><Icon name={name} />{pageTitles[id]}</a>)}</nav>
      <div className="sidebar-bottom"><div className="demo-card"><span className="mini-star">✳</span><strong>Connected to your world.</strong><p>Your phone’s camera.<br />Your visual memory.</p><span className="demo-tag">ACCOUNT WORKSPACE</span></div><div className="profile"><span className="avatar">{initials}</span><div><strong>{user.display_name}</strong><small>{user.email}</small></div></div></div>
    </aside>
    <div className="shell"><header className="topbar"><div className="breadcrumb">Workspace <span>/</span><strong>{pageTitles[page]}</strong></div><div className="top-actions"><span className="sample-indicator"><i />{selectedId ? connection : 'No session'}</span><button className="icon-button" onClick={onHelp} aria-label="Connection help"><Icon name="help" /></button><span className="avatar small">{initials}</span></div></header>
      <main id="content" tabIndex={-1} ref={mainRef}>
        <div className="session-selector toolbar"><label>Session <select value={selectedId} onChange={event => select(event.target.value)} aria-label="Choose an account session"><option value="">{loading ? 'Loading sessions…' : 'No session selected'}</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.live?.streaming ? '● LIVE · ' : ''}{new Date(session.created_at).toLocaleString()} · {session.status} · {session.id.slice(0, 8)}</option>)}</select></label><button className={`button ${followLive ? 'primary' : ''}`} aria-pressed={followLive} onClick={() => setFollowLive(value => !value)}>Follow mobile live session</button><button className="button" onClick={() => void refreshSessions().catch(() => {})}>Refresh</button></div>
        {error && <div className="notice error" role="alert">{error}<button className="text-link" onClick={() => setError('')}>Dismiss</button></div>}{mediaError && <div className="notice error" role="alert">{mediaError}<button className="text-link" onClick={() => setMediaError('')}>Dismiss</button></div>}
        {!loading && !sessions.length && <div className="notice">No retained sessions for {user.email}. Sign in with this account on mobile, consent to processing, and start assistance.</div>}
        {children}
      </main><footer><span><span className="footer-star">✳</span>Designed to bring the world a little closer.</span><span>Sora · {user.display_name}</span></footer>
    </div>
  </>;
}

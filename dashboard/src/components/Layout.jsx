import { useState } from 'react';
import Brand from './Brand.jsx';
import Icon from './Icon.jsx';
import DesignIcon from './DesignIcon.jsx';
import { pageTitles } from '../hooks/usePage.js';
import { useAuth } from '../providers/Auth.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
const navigation = [['overview', 'overview'], ['live', 'video'], ['frames', 'image'], ['questions', 'message'], ['settings', 'settings']];
export default function Layout({ page, onHelp, onSearch, mainRef, children }) {
  const { tokens } = useAuth();
  const { sessions, session, status, events, selectedId, select, followLive, setFollowLive, error, setError, mediaError, setMediaError, refreshSessions, loading } = useDashboard();
  const [query, setQuery] = useState('');
  const [notifications, setNotifications] = useState(false);
  const user = tokens.user;
  const initials = user.display_name.split(/\s+/).map(word => word[0]).slice(0, 2).join('').toUpperCase();
  return <>
    <a className="skip" href="#content" onClick={event => { event.preventDefault(); mainRef.current?.focus(); }}>Skip to content</a>
    <aside className="sidebar"><Brand /><span className="workspace-label">VISION, GIVEN A VOICE</span>
      <nav aria-label="Main navigation">{navigation.map(([id, name]) => <a key={id} href={`#${id}`} className={page === id ? 'active' : undefined} aria-current={page === id ? 'page' : undefined}><DesignIcon name={name} active={page === id} /><span>{pageTitles[id]}</span></a>)}</nav>
      <div className="sidebar-bottom"><div className="device-card"><span className={`session-badge ${status?.streaming ? 'online' : ''}`}><i />{status?.streaming ? 'Device online' : 'Device offline'}</span><strong>{status?.source ? `${status.source} camera` : 'Mobile camera'}</strong><p>{session ? `Session ${session.id.slice(0, 8)}` : 'Connect your phone to begin'}</p></div><a className="accessibility-link" href="#settings"><DesignIcon name="accessibility" /><span>Accessibility</span></a><small>Sora · Visual memory assistant</small></div>
    </aside>
    <div className="shell"><header className="topbar"><div className="mobile-brand"><Brand compact /></div><div className="breadcrumb">Workspace <span>/</span><strong>{pageTitles[page]}</strong></div><div className="top-actions">
      <form className="header-search" role="search" onSubmit={e => { e.preventDefault(); if (query.trim()) onSearch(query.trim()); }}><DesignIcon name="search" /><input type="search" value={query} onChange={e => setQuery(e.target.value)} aria-label="Search visual memory" placeholder="Search frames, objects, or recognized text" /></form>
      <div className="notification-control"><button className="icon-button" aria-label="Session notifications" aria-expanded={notifications} aria-controls="session-notifications" onClick={() => setNotifications(v => !v)}><DesignIcon name="bell" />{events.length > 0 && <i className="notification-dot" />}</button>{notifications && <section id="session-notifications" className="notification-popover" aria-label="Recent session activity"><div className="section-heading"><h2>Recent activity</h2><button className="icon-button" aria-label="Close notifications" onClick={() => setNotifications(false)}><Icon name="close" /></button></div>{events.slice(0, 5).map((event, i) => <div className="activity" key={i}><div><strong>{event.type.replaceAll('_', ' ')}</strong><p>{event.frame?.caption || event.question?.question || event.message || event.reason || event.code}</p></div><time>{new Date(event.receivedAt).toLocaleTimeString()}</time></div>)}{!events.length && <p className="muted">No recent session activity.</p>}</section>}</div>
      <button className="icon-button" onClick={onHelp} aria-label="Connection help"><Icon name="help" /></button><a href="#settings" className="avatar small" aria-label={`${user.display_name}, account settings`}>{initials}</a></div></header>
      <main id="content" tabIndex={-1} ref={mainRef}>
        {error && <div className="notice error" role="alert">{error}<button className="text-link" onClick={() => setError('')}>Dismiss</button></div>}{mediaError && <div className="notice error" role="alert">{mediaError}<button className="text-link" onClick={() => setMediaError('')}>Dismiss</button></div>}
        {!loading && !sessions.length && <div className="notice">No retained sessions for {user.email}. Sign in with this account on mobile, consent to processing, and start assistance.</div>}
        {children}
        <details className="session-picker"><summary>Session controls <span>{selectedId ? selectedId.slice(0, 8) : 'No session selected'}</span></summary><div className="session-selector toolbar"><label>Session <select value={selectedId} onChange={event => select(event.target.value)} aria-label="Choose an account session"><option value="">{loading ? 'Loading sessions…' : 'No session selected'}</option>{sessions.map(item => <option key={item.id} value={item.id}>{item.live?.streaming ? '● LIVE · ' : ''}{new Date(item.created_at).toLocaleString()} · {item.status} · {item.id.slice(0, 8)}</option>)}</select></label><button className={`button ${followLive ? 'primary' : ''}`} aria-pressed={followLive} onClick={() => setFollowLive(value => !value)}>Follow mobile live session</button><button className="button" onClick={() => void refreshSessions().catch(() => {})}>Refresh</button></div></details>
      </main><footer><span>Live video is not stored. Only selected frames enter your visual memory.</span><span>Sora · {user.display_name}</span></footer>
    </div>
  </>;
}

import Icon from './Icon.jsx';
import { frames } from '../data/demo.js';
import { pageTitles } from '../hooks/usePage.js';

const navigation = [
  ['overview', 'overview'], ['live', 'video'], ['frames', 'image'],
  ['questions', 'message'], ['settings', 'settings'],
];

export default function Layout({ page, onHelp, mainRef, children }) {
  return <>
    <a className="skip" href="#content" onClick={(event) => { event.preventDefault(); mainRef.current?.focus(); }}>Skip to content</a>
    <aside className="sidebar">
      <a className="brand" href="#overview" aria-label="Sora home"><span className="brand-mark">✳</span>sora<span className="brand-period">.</span></a>
      <span className="workspace-label">VISUAL ASSISTANCE</span>
      <nav aria-label="Main navigation">{navigation.map(([id, name]) => <NavItem key={id} id={id} name={name} page={page} />)}</nav>
      <div className="sidebar-bottom">
        <div className="demo-card"><span className="mini-star">✳</span><strong>A little more perspective.</strong><p>Meaningful moments.<br />A clearer picture.</p><span className="demo-tag">INTERACTIVE DEMO</span></div>
        <div className="profile"><span className="avatar">RK</span><div><strong>Research workspace</strong><small>University project</small></div><span className="profile-dots">···</span></div>
      </div>
    </aside>
    <div className="shell">
      <header className="topbar"><div className="breadcrumb">Workspace <span>/</span><strong>{pageTitles[page]}</strong></div><div className="top-actions"><span className="sample-indicator"><i /> Sample data</span><button className="icon-button" onClick={onHelp} aria-label="About this demo"><Icon name="help" /></button><span className="avatar small">RK</span></div></header>
      <main id="content" tabIndex={-1} ref={mainRef}>{children}</main>
      <footer><span><span className="footer-star">✳</span> Designed to bring the world a little closer.</span><span>Sora · Dashboard preview</span></footer>
    </div>
  </>;
}

function NavItem({ id, name, page }) {
  return <>
    {id === 'settings' && <div className="nav-divider" />}
    <a href={`#${id}`} className={page === id ? 'active' : undefined} aria-current={page === id ? 'page' : undefined}>
      <Icon name={name} />{pageTitles[id]}
      {id === 'live' && <span className="nav-dot" />}
      {id === 'frames' && <span className="nav-count">{frames.length}</span>}
    </a>
  </>;
}

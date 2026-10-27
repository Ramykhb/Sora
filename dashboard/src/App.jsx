import { useEffect, useRef, useState } from 'react';
import Layout from './components/Layout.jsx';
import DetailDialog from './components/DetailDialog.jsx';
import Overview from './pages/Overview.jsx';
import LiveSession from './pages/LiveSession.jsx';
import FrameLibrary from './pages/FrameLibrary.jsx';
import Conversations from './pages/Conversations.jsx';
import Preferences from './pages/Preferences.jsx';
import usePage from './hooks/usePage.js';
import { defaultPreferences } from './data/demo.js';

export default function App() {
  const page = usePage();
  const [paused, setPaused] = useState(false);
  const [preferences, setPreferences] = useState(defaultPreferences);
  const [detail, setDetail] = useState(null);
  const [toast, setToast] = useState(null);
  const mainRef = useRef(null);
  const previousPage = useRef(page);

  useEffect(() => {
    if (previousPage.current !== page) {
      setDetail(null);
      window.scrollTo(0, 0);
      mainRef.current?.focus({ preventScroll: true });
      previousPage.current = page;
    }
  }, [page]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function notify(message) { setToast({ message }); }
  function togglePause() {
    setPaused(!paused);
    notify(paused ? 'Demo preview resumed' : 'Demo preview paused');
  }
  function updatePreference(key, value) {
    setPreferences(previous => ({ ...previous, [key]: value }));
    notify('Preview preference updated');
  }
  function resetPreferences() {
    setPreferences(defaultPreferences());
    notify('Preview preferences reset');
  }
  const previewProps = { paused, showBoxes: preferences.boxes, onPause: togglePause, onExpand: () => setDetail({ type: 'preview' }) };
  const onFrame = frame => setDetail({ type: 'frame', frame });

  return <>
    <Layout page={page} onHelp={() => setDetail({ type: 'help' })} mainRef={mainRef}>
      {page === 'overview' && <Overview previewProps={previewProps} onFrame={onFrame} />}
      {page === 'live' && <LiveSession previewProps={previewProps} />}
      {page === 'frames' && <FrameLibrary onFrame={onFrame} />}
      {page === 'questions' && <Conversations onFrame={onFrame} />}
      {page === 'settings' && <Preferences preferences={preferences} onChange={updatePreference} onReset={resetPreferences} />}
    </Layout>
    <DetailDialog detail={detail} onClose={() => setDetail(null)} />
    <div id="toast" className={toast ? 'visible' : undefined} role="status" aria-live="polite">{toast?.message}</div>
  </>;
}

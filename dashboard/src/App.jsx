import { useEffect, useRef, useState } from 'react';
import Layout from './components/Layout.jsx';
import DetailDialog from './components/DetailDialog.jsx';
import AuthScreen from './components/AuthScreen.jsx';
import Overview from './pages/Overview.jsx';
import LiveSession from './pages/LiveSession.jsx';
import FrameLibrary from './pages/FrameLibrary.jsx';
import Conversations from './pages/Conversations.jsx';
import Preferences from './pages/Preferences.jsx';
import usePage from './hooks/usePage.js';
import { AuthProvider, useAuth } from './providers/Auth.jsx';
import { DashboardProvider, useDashboard } from './providers/Dashboard.jsx';
export default function App() { return <AuthProvider><Gate /></AuthProvider>; }
function Gate() {
  const { tokens } = useAuth();
  return tokens ? <DashboardProvider key={tokens.user.id}><Workspace /></DashboardProvider> : <AuthScreen />;
}
function Workspace() {
  const page = usePage();
  const { selectedId, stopSpeaking } = useDashboard();
  const [detail, setDetail] = useState(null);
  const mainRef = useRef(null);
  useEffect(() => { setDetail(null); stopSpeaking(); window.scrollTo(0, 0); mainRef.current?.focus({ preventScroll: true }); }, [page, selectedId, stopSpeaking]);
  const onFrame = (frame, onDeleted) => setDetail({ type: 'frame', frame, onDeleted });
  return <><Layout page={page} onHelp={() => setDetail({ type: 'help' })} mainRef={mainRef}>
    {page === 'overview' && <Overview onFrame={onFrame} />}{page === 'live' && <LiveSession />}{page === 'frames' && <FrameLibrary key={selectedId} onFrame={onFrame} />}{page === 'questions' && <Conversations key={selectedId} onFrame={onFrame} />}{page === 'settings' && <Preferences />}
  </Layout><DetailDialog detail={detail} onClose={() => setDetail(null)} /></>;
}

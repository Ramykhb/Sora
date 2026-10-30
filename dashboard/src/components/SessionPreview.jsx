import { useEffect, useRef, useState } from 'react';
import Icon from './Icon.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
import { subscribeVideo } from '../lib/webrtc.js';

export default function SessionPreview() {
  const { api, session, selectedId, status } = useDashboard();
  const [paused, setPaused] = useState(false);
  const [message, setMessage] = useState('Waiting for the mobile camera');
  const [live, setLive] = useState(false);
  const video = useRef(null);
  const container = useRef(null);
  useEffect(() => {
    if (!selectedId || paused) return;
    setLive(false);
    return subscribeVideo(api, selectedId, stream => {
      if (video.current) {
        video.current.srcObject = stream;
        if (stream) void video.current.play().catch(error => setMessage(error.message));
      }
      if (!stream) setLive(false);
    }, setMessage);
  }, [api, selectedId, paused]);
  return <div className={`panel ${paused ? 'paused' : ''}`} ref={container}>
    <div className="panel-head"><h2><Icon name="video" />Mobile camera <span className={`pill ${live && !paused ? '' : 'gray'}`}>{paused ? 'PAUSED' : live ? 'LIVE' : 'WAITING'}</span></h2><span className="session-label">{selectedId?.slice(0, 8)}</span></div>
    <div className="preview real-preview">
      <video ref={video} autoPlay muted playsInline onPlaying={() => setLive(true)} onWaiting={() => setLive(false)} aria-label="Live WebRTC video from the selected mobile session" hidden={!selectedId || paused} />
      {(!selectedId || !live || paused) && <div className="preview-empty" role="status">{paused ? 'Dashboard preview paused. Mobile capture continues.' : selectedId ? message : 'Sign in on mobile with this account and start assistance.'}</div>}
      <div className="preview-bottom"><div><strong>{paused ? 'Preview paused' : message}</strong><small>Account-owned session · {session?.language || '—'}</small></div><div className="preview-controls"><button onClick={() => setPaused(value => !value)} aria-label={paused ? 'Resume dashboard preview' : 'Pause dashboard preview'}><Icon name={paused ? 'play' : 'pause'} /></button><button onClick={() => void container.current?.requestFullscreen?.().catch(() => {})} aria-label="Expand mobile stream"><Icon name="expand" /></button></div></div>
    </div>
    <div className="session-footer"><span><span className="status-dot" />{session?.status || 'No session'}</span><strong>{status?.frames_received ?? 0} video frames · {status?.frames_sampled ?? 0} sampled · {status?.frames_stored ?? 0} saved</strong></div>
  </div>;
}

import { useEffect, useRef, useState } from 'react';
import DesignIcon from './DesignIcon.jsx';
import Icon from './Icon.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
import { subscribeVideo } from '../lib/webrtc.js';

export default function SessionPreview() {
  const { api, session, selectedId, status, spoken, setSpoken, stopSpeaking } = useDashboard();
  const [paused, setPaused] = useState(false);
  const [message, setMessage] = useState('Waiting for the mobile camera');
  const [live, setLive] = useState(false);
  const [resolution, setResolution] = useState('');
  const video = useRef(null);
  const container = useRef(null);
  useEffect(() => {
    setLive(false); setResolution('');
    setMessage('Waiting for the mobile camera');
    if (video.current) video.current.srcObject = null;
    if (!selectedId || paused) return;
    let disposed = false;
    const unsubscribe = subscribeVideo(api, selectedId, stream => {
      if (disposed) return;
      if (video.current) {
        video.current.srcObject = stream;
        if (stream) void video.current.play().catch(error => { if (!disposed) setMessage(error.message); });
      }
      if (!stream) setLive(false);
    }, value => { if (!disposed) setMessage(value); });
    return () => { disposed = true; unsubscribe(); if (video.current) video.current.srcObject = null; };
  }, [api, selectedId, paused]);
  return <section className={`panel stream-card ${paused ? 'paused' : ''}`} ref={container} aria-label="Live stream from device">
    <div className="panel-head"><h2>Live stream from device</h2><a className="text-link" href="#live">Open live stream ↗</a></div>
    <div className="preview real-preview">
      <video ref={video} autoPlay muted playsInline onPlaying={() => setLive(true)} onWaiting={() => setLive(false)} onLoadedMetadata={() => setResolution(`${video.current.videoWidth} × ${video.current.videoHeight}`)} aria-label="Live WebRTC video from the selected mobile session" hidden={!selectedId || paused} />
      <div className="stream-overlay"><span className={`session-badge ${live && !paused ? 'recording' : ''}`}><i />{paused ? 'PAUSED' : live ? 'LIVE' : 'WAITING'}</span>{selectedId && <span className="session-badge">Session {selectedId.slice(0, 8)}</span>}</div>
      {(!selectedId || !live || paused) && <div className="preview-empty" role="status"><DesignIcon name="video" /><span>{paused ? 'Dashboard preview paused. Mobile capture continues.' : selectedId ? message : 'Sign in on mobile with this account and start assistance.'}</span></div>}
    </div>
    <div className="stream-controls"><button className="button" aria-pressed={spoken} onClick={() => { setSpoken(!spoken); if (spoken) stopSpeaking(); }}><DesignIcon name="sound" />{spoken ? 'Spoken answers on' : 'Spoken answers off'}</button><span className="stream-meta">{resolution || session?.language?.toUpperCase() || 'No camera connected'}{status?.streaming && ` · ${status.frames_received ?? 0} frames`}</span><div className="stream-control-actions"><button className="icon-button" onClick={() => setPaused(value => !value)} aria-label={paused ? 'Resume dashboard preview' : 'Pause dashboard preview'}><Icon name={paused ? 'play' : 'pause'} /></button><button className="button" onClick={() => void container.current?.requestFullscreen?.().catch(() => {})}><DesignIcon name="expand" />Full screen</button></div></div>
    <div className="stream-caption"><span className={`status-dot ${live ? 'online' : ''}`} />{paused ? 'Preview paused' : message}</div>
  </section>;
}

import { useEffect, useRef, useState } from 'react';
import Icon from './Icon.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
import { MjpegParser } from '../lib/live.js';

export default function SessionPreview() {
  const { api, session, selectedId, status } = useDashboard();
  const [paused, setPaused] = useState(false);
  const [message, setMessage] = useState('Waiting for the mobile camera');
  const [live, setLive] = useState(false);
  const canvas = useRef(null);
  const container = useRef(null);
  useEffect(() => {
    if (!selectedId || paused) return;
    let disposed = false;
    let controller;
    let timer;
    let idle;
    let retry = 1000;
    async function connect() {
      controller = new AbortController();
      let reader;
      try {
        setLive(false); setMessage('Connecting to the mobile camera…');
        const response = await api.response(`/sessions/${selectedId}/stream/live.mjpeg`, { signal: controller.signal }, 0);
        if (!response.body) throw new Error('This browser cannot read live video.');
        reader = response.body.getReader();
        const parser = new MjpegParser();
        while (!disposed) {
          idle = setTimeout(() => controller.abort(), 20000);
          const { value, done } = await reader.read();
          clearTimeout(idle);
          if (done) throw new Error('Mobile stream disconnected. Waiting to reconnect…');
          const jpeg = parser.push(value).at(-1);
          if (!jpeg) continue;
          const image = await createImageBitmap(new Blob([jpeg], { type: 'image/jpeg' }));
          try {
            if (disposed || !canvas.current) break;
            canvas.current.width = image.width; canvas.current.height = image.height;
            canvas.current.getContext('2d').drawImage(image, 0, 0);
            setLive(true); setMessage('Live from mobile'); retry = 1000;
          } finally { image.close(); }
        }
      } catch (e) {
        if (!disposed) { setLive(false); setMessage(e.status === 409 ? 'No camera is streaming. Start assistance on mobile with this account.' : e.name === 'AbortError' ? 'Stream interrupted. Reconnecting…' : e.message); }
      } finally {
        clearTimeout(idle);
        await reader?.cancel().catch(() => {});
        controller.abort();
        if (!disposed) { timer = setTimeout(() => void connect(), retry); retry = Math.min(10000, retry * 2); }
      }
    }
    void connect();
    return () => { disposed = true; controller?.abort(); clearTimeout(timer); clearTimeout(idle); };
  }, [api, selectedId, paused]);
  return <div className={`panel ${paused ? 'paused' : ''}`} ref={container}>
    <div className="panel-head"><h2><Icon name="video" />Mobile camera <span className={`pill ${live && !paused ? '' : 'gray'}`}>{paused ? 'PAUSED' : live ? 'LIVE' : 'WAITING'}</span></h2><span className="session-label">{selectedId?.slice(0, 8)}</span></div>
    <div className="preview real-preview">
      <canvas ref={canvas} aria-label="Live camera stream from the selected mobile session" hidden={!selectedId || !live || paused} />
      {(!selectedId || !live || paused) && <div className="preview-empty" role="status">{paused ? 'Dashboard preview paused. Mobile capture continues.' : selectedId ? message : 'Sign in on mobile with this account and start assistance.'}</div>}
      <div className="preview-bottom"><div><strong>{paused ? 'Preview paused' : message}</strong><small>Account-owned session · {session?.language || '—'}</small></div><div className="preview-controls"><button onClick={() => setPaused(value => !value)} aria-label={paused ? 'Resume dashboard preview' : 'Pause dashboard preview'}><Icon name={paused ? 'play' : 'pause'} /></button><button onClick={() => void container.current?.requestFullscreen?.().catch(() => {})} aria-label="Expand mobile stream"><Icon name="expand" /></button></div></div>
    </div>
    <div className="session-footer"><span><span className="status-dot" />{session?.status || 'No session'}</span><strong>{status?.frames_received ?? 0} received · {status?.frames_stored ?? 0} saved</strong></div>
  </div>;
}

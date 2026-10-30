import { useEffect, useRef, useState } from 'react';
import Icon from './Icon.jsx';
import ProtectedImage from './ProtectedImage.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
export default function DetailDialog({ detail, onClose }) {
  const { api, refreshData, refreshSessions, setError, frames } = useDashboard();
  const dialogRef = useRef(null);
  const [original, setOriginal] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (detail && !dialog.open) dialog.showModal();
    if (!detail && dialog.open) dialog.close();
  }, [detail]);
  const frame = frames.find(item => item.id === detail?.frame?.id) || detail?.frame;
  async function remove() {
    if (!window.confirm('Permanently delete this image?')) return;
    setBusy(true);
    try { await api.request(`/sessions/${frame.session_id}/frames/${frame.id}`, 'DELETE'); detail.onDeleted?.(frame.id); onClose(); await Promise.all([refreshData(), refreshSessions()]); }
    catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  return <dialog id="detail-dialog" ref={dialogRef} aria-labelledby="dialog-title" onClose={onClose} onClick={event => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }}>
    <div className="dialog-top"><span className="eyebrow">{frame ? 'FRAME DETAILS' : 'SORA'}</span><button className="icon-button" onClick={onClose} aria-label="Close details"><Icon name="close" /></button></div>
    {frame ? <><ProtectedImage path={`/sessions/${frame.session_id}/frames/${frame.id}/image?original=${original}`} alt={frame.caption || 'Saved camera frame'} /><h2 id="dialog-title">{frame.caption || (frame.enrichment_status === 'pending' ? 'Saved · description processing' : 'Saved scene')}</h2><button className="button" onClick={() => setOriginal(value => !value)}>{original ? 'Show enhanced image' : 'Show sanitized original'}</button><dl><dt>Frame ID</dt><dd>{frame.id}</dd><dt>Captured</dt><dd>{new Date(frame.captured_at).toLocaleString()}</dd><dt>Objects</dt><dd>{frame.detected_objects?.map(o => `${o.label} (${Math.round(o.confidence * 100)}%)`).join(', ') || 'None detected'}</dd><dt>Recognized text</dt><dd>{frame.ocr_text || 'No text recognized'}</dd><dt>Saved after</dt><dd>{Math.round(frame.processing_ms)} ms</dd><dt>AI description</dt><dd>{frame.enrichment_status === 'pending' ? 'Processing in background' : frame.enrichment_status === 'failed' ? 'Unavailable — see warnings' : frame.enrichment_ms == null ? 'Complete' : `Completed in ${(frame.enrichment_ms / 1000).toFixed(1)} s`}</dd><dt>Expires</dt><dd>{new Date(frame.expires_at).toLocaleString()}</dd></dl>{frame.processing_warnings?.map(w => <div className="notice error" key={w}>{w}</div>)}<button className="button danger" disabled={busy} onClick={() => void remove()}>Delete image</button></> : <><h2 id="dialog-title">Your mobile view, connected.</h2><p>Sign in on the phone and dashboard with the same account. Start a capture session on mobile; the dashboard automatically follows its live stream.</p><p>The session selector lets you revisit retained sessions. Conversations, images and alerts are shared through the backend. Pausing this preview leaves mobile capture running. Ending a capture session stops its producer and keeps memory until expiry.</p></>}
  </dialog>;
}

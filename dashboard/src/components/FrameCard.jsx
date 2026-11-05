import ProtectedImage from './ProtectedImage.jsx';
export default function FrameCard({ frame, onSelect, compact = false }) {
  return <button className="frame-card" onClick={() => onSelect(frame)} aria-label={`View ${frame.caption || 'saved frame'}`}>
    <div className="frame-image"><ProtectedImage path={`/sessions/${frame.session_id}/frames/${frame.id}/image`} alt={frame.caption || 'Retained camera image'} />{!compact && <span className="frame-time">{new Date(frame.captured_at).toLocaleString()}</span>}</div>
    {compact && <time className="timeline-time" dateTime={frame.captured_at}>{new Date(frame.captured_at).toLocaleTimeString([], { hour12: false })}</time>}
    <div className="frame-copy"><strong>{frame.caption || (['pending', 'processing'].includes(frame.enrichment_status || '') ? 'Saved · description processing' : 'Scene captured')}</strong><div className="frame-tags">{frame.detected_objects?.slice(0, 5).map((object, index) => <span key={index}>{object.label}</span>)}{!!frame.ocr_text && <span>Text detected</span>}</div></div>
  </button>;
}

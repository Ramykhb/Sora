import ProtectedImage from './ProtectedImage.jsx';
export default function FrameCard({ frame, onSelect }) {
  return <button className="frame-card" onClick={() => onSelect(frame)} aria-label={`View ${frame.caption || 'saved frame'}`}>
    <div className="frame-image"><ProtectedImage path={`/sessions/${frame.session_id}/frames/${frame.id}/image`} alt={frame.caption || 'Retained camera image'} /><span className="frame-time">{new Date(frame.captured_at).toLocaleString()}</span></div>
    <div className="frame-copy"><strong>{frame.caption || 'Scene captured'}</strong><div className="frame-tags">{frame.detected_objects?.slice(0, 5).map((object, index) => <span key={index}>{object.label}</span>)}{!!frame.ocr_text && <span>Text detected</span>}</div></div>
  </button>;
}

import { useEffect, useRef } from 'react';
import Icon from './Icon.jsx';
import scene from '../../assets/scene.svg';

export default function DetailDialog({ detail, onClose }) {
  const dialogRef = useRef(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (detail && !dialog.open) dialog.showModal();
    if (!detail && dialog.open) dialog.close();
  }, [detail]);
  const frame = detail?.frame;
  return <dialog id="detail-dialog" ref={dialogRef} aria-labelledby="dialog-title" onClose={onClose} onClick={event => {
    if (event.target !== event.currentTarget) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
  }}>
    <div className="dialog-top"><span className="eyebrow">{frame ? 'FRAME DETAILS' : 'SORA PREVIEW'}</span><button className="icon-button" onClick={onClose} aria-label="Close details"><Icon name="close" /></button></div>
    {frame ? <><img src={scene} alt="Illustrated sample room" /><h2 id="dialog-title">{frame.title}</h2><p>{frame.caption}</p><dl><dt>Frame ID</dt><dd>{frame.id}</dd><dt>Captured</dt><dd>{frame.date} · {frame.time}</dd><dt>Objects</dt><dd>{frame.tags.join(', ')}</dd><dt>Recognized text</dt><dd>{frame.ocr}</dd><dt>Quality score</dt><dd>{frame.quality} / 100 (sample)</dd></dl><div className="notice">Illustrative demo data · no images have been retrieved from your backend.</div></> : detail?.type === 'preview' ? <><h2 id="dialog-title">Study room · demo preview</h2><img src={scene} alt="Illustrated study room with a table, plant and exit door" /><p>Sample stream · Session #SR-0042 · No camera connected.</p></> : <><h2 id="dialog-title">A clearer view, with Sora.</h2><p>This dashboard is an interactive design preview for a visual assistance project. Explore a sample session, browse saved moments and review question history.</p><p>All metrics, answers and detections are sample data. The room is a local SVG illustration. There are no API requests, camera permissions or backend connections.</p></>}
  </dialog>;
}

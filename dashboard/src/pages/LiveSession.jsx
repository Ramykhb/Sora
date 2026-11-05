import SessionActions from '../components/SessionActions.jsx';
import { Heading } from '../components/Shared.jsx';
import SessionPreview from '../components/SessionPreview.jsx';
import QuestionComposer from '../components/QuestionComposer.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
import { descriptionStatus } from '../lib/observations.js';
export default function LiveSession() {
  const { selectedId, frames, status, observation, alerts } = useDashboard();
  const frame = frames[0];
  const description = frame ? descriptionStatus(frame) : 'Waiting for a processed frame.';
  return <>
    <Heading title="A little closer to the moment." subtitle="Live video from your mobile account, with shared scene context."><SessionActions /></Heading>
    <section className="panel"><div className="panel-head"><h2>Live object detection</h2></div><div className="panel-body">{observation ? <><p>{observation.detected_objects.length ? observation.detected_objects.map(object => `${object.label} (${Math.round(object.confidence * 100)}%)`).join(', ') : 'No supported objects detected. This does not establish that the route is clear.'}</p><p className="muted">Server detection latency: {Math.round(observation.latency_ms)} ms · captured {new Date(observation.captured_at).toLocaleTimeString()}</p></> : <p>Waiting for fresh detections.</p>}{status?.detection_error && <p role="alert">Live detection unavailable: {status.detection_error}</p>}</div></section>
    <div className="live-layout"><SessionPreview /><div><div className="panel"><div className="panel-head"><h2>Latest saved scene</h2></div><div className="panel-body"><p>{description}</p>{frame && <p className="muted">Captured {new Date(frame.captured_at).toLocaleString()}. Detections describe this saved frame.</p>}</div>{frame?.detected_objects?.map((object, index) => <div className="detection" key={index}>{object.label}<span>{Math.round(object.confidence * 100)}%</span></div>)}<div className="panel-head"><h2>Recognized text</h2></div><div className="panel-body">{frame?.ocr_text || 'No text recognized'}</div></div><div className="notice live-notice">Received {status?.frames_received ?? 0} · sampled {status?.frames_sampled ?? 0} · saved {status?.frames_stored ?? 0} · rejected {status?.frames_rejected ?? 0} · dropped {status?.frames_dropped ?? 0}{status?.processing_error && <p role="alert">{status.processing_error}</p>}</div></div></div>
    <QuestionComposer key={selectedId} />
    <section className="panel"><div className="panel-head"><h2>Session alerts</h2></div>{alerts.length ? alerts.map((alert, index) => <div className="panel-body" key={alert.id || index}><strong>{alert.message}</strong><p className="muted">{new Date(alert.created_at).toLocaleString()}</p></div>) : <div className="empty">No retained alerts.</div>}</section>
  </>;
}

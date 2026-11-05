import { Heading, SectionHeading } from '../components/Shared.jsx';
import FrameCard from '../components/FrameCard.jsx';
import SessionPreview from '../components/SessionPreview.jsx';
import SessionActions from '../components/SessionActions.jsx';
import DesignIcon from '../components/DesignIcon.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
import { dashboardStatus, latencyLabel } from '../lib/status.js';
function StatusPanel() {
  const { metrics, frames, selectedId, connection, status, error } = useDashboard();
  const health = dashboardStatus({ selectedId, connection, status, error });
  return <section className="panel status-panel" aria-label="Live status"><div className="panel-head"><h2>Live status</h2><span className="status-summary">{health.healthy ? 'Systems online' : 'Session status'}</span></div>
    <div className="health-summary"><div className={`health-ring ${health.healthy ? 'healthy' : ''}`} aria-hidden="true" /><div><strong>{health.label}</strong><p className={health.healthy ? 'good' : 'muted'}>{health.detail}</p></div></div>
    <div className="status-metric green"><div><span>Server connection</span><strong>{selectedId ? connection : 'No session'}</strong></div><div className="metric-track"><span style={{ width: health.connected ? '100%' : '0%' }} /></div></div>
    <div className="status-metric purple"><div><span>Avg. frame processing</span><strong>{latencyLabel(metrics?.mean_frame_processing_ms)}</strong></div><div className="metric-track" aria-hidden="true"><span className={metrics?.mean_frame_processing_ms == null ? '' : 'measured'} /></div></div>
    <div className="status-metric pink"><div><span>Avg. answer response</span><strong>{latencyLabel(metrics?.mean_question_latency_ms)}</strong></div><div className="metric-track" aria-hidden="true"><span className={metrics?.mean_question_latency_ms == null ? '' : 'measured'} /></div></div>
    <div className="memory-status"><strong>{status?.processing_error ? 'Frame processing needs attention' : frames.length ? 'Visual memory is available' : 'Waiting for visual memory'}</strong><p>{frames[0] ? <>Last saved <time dateTime={frames[0].captured_at}>{new Date(frames[0].captured_at).toLocaleTimeString()}</time> · {metrics?.retained_frames ?? frames.length} retained frames</> : 'Selected frames will appear here automatically'}</p></div>
  </section>;
}
export default function Overview({ onFrame }) {
  const { frames, questions, session, api, play, stopSpeaking, setMediaError, setError } = useDashboard();
  async function evidence(answer) {
    const id = answer.evidence_frame_ids?.[0];
    if (!id) return;
    try { onFrame(frames.find(frame => frame.id === id) || await api.request(`/sessions/${answer.session_id}/frames/${id}`)); }
    catch (error) { setError(error.message); }
  }
  return <div className="dashboard-overview">
    <Heading title="Your world, in real time." subtitle="Follow the live view, revisit moments, and hear what Sora sees."><SessionActions /></Heading>
    <div className="monitoring-grid"><SessionPreview /><StatusPanel /></div>
    <div className="memory-grid"><section className="panel timeline-panel"><SectionHeading title="Frame timeline" link="View all frames ↗" page="frames" /><p className="panel-subtitle">Moments worth remembering, saved automatically.</p>
      <div className="timeline-frames">{frames.slice(0, 3).map(frame => <FrameCard compact key={frame.id} frame={frame} onSelect={onFrame} />)}{!frames.length && <div className="empty"><DesignIcon name="image" /><strong>No saved moments yet</strong><p>{session ? 'Useful frames from your camera will appear here.' : 'Start assistance on your phone to build visual memory.'}</p></div>}</div>
      <p className="retention-note"><span className="status-dot online" />Faces blurred in saved frames · Frames expire automatically</p>
    </section>
    <section className="panel qa-panel"><SectionHeading title="Q&A history" link="View conversation ↗" page="questions" />
      <div className="qa-list">{questions.slice(0, 2).map(answer => <article className="qa-item" key={answer.id}><div className="qa-question"><DesignIcon name="mic" /><strong dir="auto">{answer.question}</strong><time dateTime={answer.created_at}>{new Date(answer.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div><div className="qa-answer"><DesignIcon name="answer" /><div><p dir="auto">{answer.answer}</p>{answer.uncertain && <span className="pill amber">Uncertain</span>}<div className="qa-actions"><button className="text-link" onClick={() => void play(`/sessions/${answer.session_id}/questions/${answer.id}/audio`).catch(e => setMediaError(e.message))}>Replay answer</button><span>·</span><button className="text-link" onClick={stopSpeaking}>Stop</button>{answer.evidence_frame_ids?.length > 0 && <><span>·</span><button className="text-link" onClick={() => void evidence(answer)}>View source frame ↗</button></>}</div></div></div></article>)}{!questions.length && <div className="empty"><DesignIcon name="message" /><strong>Your conversations, together</strong><p>Ask Sora on your phone or open Q&A History to ask a question.</p><a href="#questions" className="text-link">Ask Sora ↗</a></div>}</div>
    </section></div>
  </div>;
}

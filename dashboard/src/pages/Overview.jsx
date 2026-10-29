import { Heading, SectionHeading } from '../components/Shared.jsx';
import FrameCard from '../components/FrameCard.jsx';
import SessionPreview from '../components/SessionPreview.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
export default function Overview({ onFrame }) {
  const { metrics, frames, questions, events, session } = useDashboard();
  const stats = [
    ['Saved frames', metrics?.retained_frames ?? '—', 'Retained across your sessions'],
    ['Questions answered', metrics?.retained_questions ?? '—', 'Your stored conversations'],
    ['Avg. response time', metrics?.mean_question_latency_ms == null ? '—' : `${(metrics.mean_question_latency_ms / 1000).toFixed(1)} s`, 'Measured by the backend'],
    ['Live sessions', metrics?.live_sessions ?? '—', 'Your connected producers'],
  ];
  return <>
    <Heading title="A clearer view of today." subtitle="Your mobile camera, visual memory and conversations, together."><a className="button" href="#frames">Explore moments</a><a className="button primary" href="#live">View mobile stream</a></Heading>
    <div className="stats">{stats.map(([label, value, note]) => <div className="stat" key={label}><div className="stat-top">{label}</div><div className="stat-value">{value}</div><div className="stat-bottom">{note}</div></div>)}</div>
    <div className="columns"><SessionPreview /><div className="panel"><div className="panel-head"><h2>Recent activity</h2><span className="pill gray">EVENTS</span></div><div className="activity-list">{events.slice(0, 6).map((event, index) => <div className="activity" key={index}><div className="activity-copy"><strong>{event.type.replaceAll('_', ' ')}</strong><p>{event.frame?.caption || event.question?.question || event.message || event.reason || event.code}</p></div><time>{new Date(event.receivedAt).toLocaleTimeString()}</time></div>)}{!events.length && <div className="empty">{session ? 'Waiting for session activity.' : 'Start assistance on mobile to see activity.'}</div>}</div></div></div>
    <SectionHeading title="Recent moments" subtitle="Selected camera frames from this session." link="Explore library" page="frames" />
    <div className="frames">{frames.slice(0, 4).map(frame => <FrameCard key={frame.id} frame={frame} onSelect={onFrame} />)}</div>
    {!frames.length && <div className="notice">No retained frames in the selected session.</div>}
    <SectionHeading title="Questions & answers" subtitle="Shared with your mobile account." link="View conversations" page="questions" />
    <div className="panel">{questions.slice(0, 4).map(question => <div className="question-row" key={question.id}><span className="question">{question.question}</span><span className="answer">{question.answer.slice(0, 130)}</span><span className={`pill ${question.uncertain ? 'amber' : ''}`}>{question.uncertain ? 'Uncertain' : 'Answered'}</span><time>{new Date(question.created_at).toLocaleTimeString()}</time></div>)}{!questions.length && <div className="empty">No questions yet.</div>}</div>
  </>;
}

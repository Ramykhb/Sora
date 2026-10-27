import Icon from '../components/Icon.jsx';
import { Heading, SectionHeading } from '../components/Shared.jsx';
import FrameCard from '../components/FrameCard.jsx';
import SessionPreview from '../components/SessionPreview.jsx';
import { frames, questions } from '../data/demo.js';

const stats = [
  { label: 'Saved frames', value: '248', icon: 'image', note: <><b>+24</b> in this session</> },
  { label: 'Questions answered', value: '32', icon: 'message', note: <><b>28 grounded</b> in visual evidence</> },
  { label: 'Avg. response time', value: <>1.8 <small>s</small></>, icon: 'clock', note: 'Sample session average' },
  { label: 'Languages used', value: <>2 <small>/ 3</small></>, icon: 'globe', note: 'English · Français · العربية' },
];
const activity = [
  ['image', 'A new moment captured', 'Door, table and exit sign', 'Just now'],
  ['message', 'A question answered', '“What’s in front of me?”', '1m ago'],
  ['image', 'Text recognized', 'EXIT →', '2m ago'],
  ['globe', 'Language switched', 'Français → English', '4m ago'],
];

export default function Overview({ previewProps, onFrame }) {
  return <>
    <Heading title="A clearer view of today." subtitle="Every moment captured. Every question in context."><a className="button" href="#frames"><Icon name="clock" /> Today’s moments</a><a className="button primary" href="#live"><Icon name="video" /> View session</a></Heading>
    <div className="stats">{stats.map((stat, index) => <div className="stat" key={stat.label}><div className="stat-top">{stat.label}<Icon name={stat.icon} /></div><div className="stat-value">{stat.value}</div><div className="stat-bottom">{stat.note}</div>{index < 2 && <svg className="spark" viewBox="0 0 100 30" aria-hidden="true"><path d="M0 25 10 20 20 23 30 12 40 15 50 8 60 13 70 5 80 8 90 2 100 5" /></svg>}</div>)}</div>
    <div className="columns"><SessionPreview {...previewProps} /><div className="panel"><div className="panel-head"><h2>Recent activity</h2><span className="pill gray">SAMPLE</span></div><div className="activity-list">{activity.map(([name, title, description, time]) => <div className="activity" key={title}><div className="activity-icon"><Icon name={name} /></div><div className="activity-copy"><strong>{title}</strong><p>{description}</p></div><time>{time}</time></div>)}</div><div className="activity-foot"><span className="status-dot" /> A snapshot of a sample session</div></div></div>
    <SectionHeading title="Recent moments" subtitle="A visual memory of the things that matter." link="Explore library" page="frames" />
    <div className="frames">{frames.slice(0, 4).map(frame => <FrameCard key={frame.id} frame={frame} onSelect={onFrame} />)}</div>
    <SectionHeading title="Questions & answers" subtitle="Small questions. A little more understanding." link="View conversations" page="questions" />
    <div className="panel"><div className="question-row table-head"><span>QUESTION</span><span>ANSWER PREVIEW</span><span>CONFIDENCE</span><span>TIME</span></div>{questions.slice(0, 3).map(question => <div className="question-row" key={question.q}><span className="question"><Icon name="message" />{question.q}</span><span className="answer">{question.a.substring(0, 71)}…</span><span className="pill">{question.status}</span><time>{question.time}</time></div>)}</div>
  </>;
}

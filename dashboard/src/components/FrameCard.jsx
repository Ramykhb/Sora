import Icon from './Icon.jsx';
import scene from '../../assets/scene.svg';

export default function FrameCard({ frame, onSelect }) {
  return <button className="frame-card" onClick={() => onSelect(frame)} aria-label={`View ${frame.title}`}>
    <div className={`frame-image scene-${frame.scene}`}><img src={scene} alt="" loading="lazy" /><span className="frame-time">{frame.time}</span><span className="frame-mark"><Icon name={frame.type === 'Text detected' ? 'message' : 'image'} /></span></div>
    <div className="frame-copy"><strong>{frame.title}</strong><div className="frame-tags">{frame.tags.map(tag => <span key={tag}>{tag}</span>)}</div></div>
  </button>;
}

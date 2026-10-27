import Icon from './Icon.jsx';
import scene from '../../assets/scene.svg';

export default function SessionPreview({ paused, showBoxes, onPause, onExpand }) {
  return <div className={`panel ${paused ? 'paused' : ''}`}>
    <div className="panel-head"><h2><Icon name="video" />Session preview <span className="pill gray">DEMO</span></h2><span className="session-label">Session #SR-0042</span></div>
    <div className="preview">
      <img src={scene} alt="Illustrated demo scene of a study room with a table, plant and exit door" />
      <span className="preview-label"><i />{paused ? 'PAUSED' : 'SAMPLE STREAM'}</span><span className="preview-time">00:12:34</span>
      {showBoxes && <><div className="box door"><span>Door · 98%</span></div><div className="box table"><span>Table · 96%</span></div><div className="box plant"><span>Plant · 94%</span></div></>}
      <div className="preview-bottom"><div><strong>Study room</strong><small>Illustrative preview · no camera connected</small></div><div className="preview-controls"><button onClick={onPause} aria-label={`${paused ? 'Resume' : 'Pause'} demo preview`}><Icon name={paused ? 'play' : 'pause'} /></button><button onClick={onExpand} aria-label="Expand demo preview"><Icon name="expand" /></button></div></div>
    </div>
    <div className="session-footer"><span><span className="status-dot" /> {paused ? 'Preview paused' : 'Demo session'} <span className="muted">· English</span></span><strong>3 objects detected</strong></div>
  </div>;
}

import Icon from '../components/Icon.jsx';
import { Heading } from '../components/Shared.jsx';
import SessionPreview from '../components/SessionPreview.jsx';

export default function LiveSession({ previewProps }) {
  return <>
    <Heading title="A little closer to the moment." subtitle="An illustrated session preview with sample object detections."><button className="button primary" onClick={previewProps.onPause}><Icon name={previewProps.paused ? 'play' : 'pause'} />{previewProps.paused ? 'Resume preview' : 'Pause preview'}</button></Heading>
    <div className="notice">Demo mode · This preview uses an illustration. No camera, stream or AI service is connected.</div>
    <div className="live-layout"><SessionPreview {...previewProps} /><div><div className="panel"><div className="panel-head"><h2>In this scene</h2><span className="pill">3 objects</span></div>{[['Door', '98%'], ['Table', '96%'], ['Potted plant', '94%']].map(([label, confidence]) => <div className="detection" key={label}>{label}<span>{confidence}</span></div>)}<div className="panel-head"><h2>Recognized text</h2></div><div className="detection">EXIT → <span>English</span></div></div><div className="notice live-notice">Visual assistance adds context. It cannot confirm whether a path is safe to walk.</div></div></div>
  </>;
}

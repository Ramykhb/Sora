import Icon from '../components/Icon.jsx';
import { Heading, Select } from '../components/Shared.jsx';

function Setting({ title, description, children }) {
  return <div className="setting"><div><strong>{title}</strong><p>{description}</p></div>{children}</div>;
}

export default function Preferences({ preferences, onChange, onReset }) {
  const toggle = (key, title, description) => <Setting title={title} description={description}><button className="switch" role="switch" aria-label={title} aria-checked={preferences[key]} onClick={() => onChange(key, !preferences[key])} /></Setting>;
  return <>
    <Heading title="Make it feel like you." subtitle="Explore display and assistance preferences in this UI demo." />
    <div className="notice">Preview preferences apply only to this page. Nothing is sent to or saved on a server.</div>
    <div className="settings-grid"><div className="panel"><div className="panel-head"><h2><Icon name="spark" /> Assistance</h2></div><div className="settings-body">
      {toggle('spoken', 'Spoken answers', 'Show your preferred answer delivery setting.')}
      {toggle('alerts', 'Obstacle alerts', 'Show your preferred proactive alert setting.')}
      <Setting title="Preferred language" description="Language for a future connected session."><Select label="Preferred language" value={preferences.language} onChange={value => onChange('language', value)} options={['English', 'Français', 'العربية']} /></Setting>
    </div></div><div className="panel"><div className="panel-head"><h2><Icon name="shield" /> Display & privacy</h2></div><div className="settings-body">
      {toggle('boxes', 'Object outlines', 'Display detections on the sample preview.')}
      <Setting title="Frame retention" description="Preview a preferred retention period."><Select label="Frame retention" value={preferences.retention} onChange={value => onChange('retention', value)} options={['1 hour', '24 hours', '7 days']} /></Setting>
      <Setting title="Reset preview" description="Restore the default UI preferences."><button className="button" onClick={onReset}>Reset</button></Setting>
    </div></div></div>
  </>;
}

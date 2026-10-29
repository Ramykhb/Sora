import { useState } from 'react';
import { useDashboard } from '../providers/Dashboard.jsx';
export default function SpeechTools() {
  const { api, play, stopSpeaking, setError } = useDashboard();
  const [text, setText] = useState('');
  const [language, setLanguage] = useState('en');
  const [busy, setBusy] = useState(false);
  async function transcribe(file) {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const form = new FormData(); form.append('audio', file); form.append('language', language);
      const result = await api.upload('/speech/transcriptions', form);
      setText(result.text); setLanguage(result.language);
    } catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  return <section className="panel panel-body form-stack"><h2>Speech tools</h2><p>Transcribe an audio file or synthesize a spoken message using the backend.</p>
    <label>Language<select value={language} onChange={e => setLanguage(e.target.value)}><option value="en">English</option><option value="fr">Français</option><option value="ar">العربية</option></select></label><label>Audio file<input type="file" accept="audio/*" disabled={busy} onChange={event => { void transcribe(event.target.files?.[0]); event.target.value = ''; }} /></label>
    <label>Text<textarea maxLength={1000} value={text} onChange={e => setText(e.target.value)} dir="auto" /></label><div className="action-row"><button className="button" disabled={busy || !text.trim()} onClick={() => void play('/speech/synthesis', { text, language }).catch(e => setError(e.message))}>Speak text</button><button className="button" onClick={stopSpeaking}>Stop audio</button></div>
  </section>;
}

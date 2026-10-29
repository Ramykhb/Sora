import { useEffect, useRef, useState } from 'react';
import { useDashboard } from '../providers/Dashboard.jsx';
export default function QuestionComposer() {
  const { api, selectedId, session, refreshData, setError, stopSpeaking } = useDashboard();
  const [question, setQuestion] = useState('');
  const [scope, setScope] = useState('recent');
  const [language, setLanguage] = useState(session?.language || 'en');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const recorder = useRef(null);
  const tracks = useRef(null);
  const timeout = useRef(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const cancel = () => {
      if (recorder.current) { recorder.current.onstop = null; if (recorder.current.state !== 'inactive') recorder.current.stop(); }
      tracks.current?.getTracks().forEach(track => track.stop());
      clearTimeout(timeout.current); setRecording(false);
    };
    const hide = () => { if (document.hidden) cancel(); };
    document.addEventListener('visibilitychange', hide);
    return () => { mounted.current = false; cancel(); document.removeEventListener('visibilitychange', hide); };
  }, []);
  async function receive(answer) {
    if (!mounted.current) return;
    setQuestion(''); await refreshData();

  }
  function bounds() {
    const result = {};
    if (scope !== 'memory') return result;
    if (since) result.since = new Date(since).toISOString();
    if (until) result.until = new Date(until).toISOString();
    return result;
  }
  async function ask(event) {
    event.preventDefault(); setBusy(true); setError(''); stopSpeaking();
    try { await receive(await api.request(`/sessions/${selectedId}/questions`, 'POST', { question, scope, language, ...bounds() })); }
    catch (error) { if (mounted.current) setError(error.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function voice() {
    if (recording) { recorder.current?.stop(); return; }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Voice recording requires a supported browser on localhost or HTTPS.'); return; }
    setBusy(true); setError(''); stopSpeaking();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mounted.current || document.hidden) { stream.getTracks().forEach(track => track.stop()); return; }
      tracks.current = stream;
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type));
      const capture = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks = [];
      recorder.current = capture;
      capture.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      capture.onerror = () => { setError('Microphone recording failed.'); if (capture.state !== 'inactive') capture.stop(); };
      capture.onstop = async () => {
        clearTimeout(timeout.current); stream.getTracks().forEach(track => track.stop());
        if (!mounted.current) return;
        setRecording(false); setBusy(true);
        try {
          const audio = new Blob(chunks, { type: capture.mimeType });
          const form = new FormData(); form.append('audio', audio, capture.mimeType.includes('mp4') ? 'question.m4a' : 'question.webm');
          form.append('language', language); form.append('scope', scope);
          if (scope === 'memory' && (since || until)) {
            const transcript = await api.upload('/speech/transcriptions', form);
            await receive(await api.request(`/sessions/${selectedId}/questions`, 'POST', { question: transcript.text, language, scope, ...bounds() }));
          } else await receive(await api.upload(`/sessions/${selectedId}/questions/audio`, form));
        } catch (error) { if (mounted.current) setError(error.message); }
        finally { if (mounted.current) setBusy(false); }
      };
      capture.start(); setRecording(true); timeout.current = setTimeout(() => { if (capture.state !== 'inactive') capture.stop(); }, 55000);
    } catch (error) { tracks.current?.getTracks().forEach(track => track.stop()); setError(error.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <section className="panel composer"><h2>Ask Sora</h2><form onSubmit={ask} className="form-stack">
    <label>Question<textarea value={question} onChange={e => setQuestion(e.target.value)} maxLength={2000} placeholder="What can you see? What did that sign say?" required disabled={!selectedId || busy || recording} /></label>
    <div className="toolbar"><label>Evidence<select value={scope} onChange={e => setScope(e.target.value)} disabled={recording || busy}><option value="recent">Current view</option><option value="memory">Retained memory</option><option value="auto">Auto</option></select></label><label>Language<select value={language} onChange={e => setLanguage(e.target.value)} disabled={recording || busy}><option value="en">English</option><option value="fr">Français</option><option value="ar">العربية</option></select></label></div>
    {scope === 'memory' && <div className="toolbar"><label>Since<input type="datetime-local" value={since} onChange={e => setSince(e.target.value)} /></label><label>Until<input type="datetime-local" value={until} onChange={e => setUntil(e.target.value)} /></label></div>}
    <div className="action-row"><button className="button primary" disabled={!selectedId || busy || recording || !question.trim()}>{busy ? 'Processing…' : 'Ask question'}</button><button type="button" className="button" disabled={!selectedId || busy} onClick={() => void voice()}>{recording ? 'Stop recording and send' : 'Record voice question'}</button><button type="button" className="button" onClick={stopSpeaking}>Stop audio</button></div>{recording && <p role="status">Recording… tap again to send. Stops automatically at 55 seconds.</p>}
  </form></section>;
}

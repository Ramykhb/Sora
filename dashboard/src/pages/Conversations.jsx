import { useState } from 'react';
import { Heading, SearchInput, Select } from '../components/Shared.jsx';
import QuestionComposer from '../components/QuestionComposer.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
function AnswerCard({ answer, onFrame }) {
  const { api, play, stopSpeaking, setError } = useDashboard();
  const [rating, setRating] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  async function feedback(value) {
    setBusy(true);
    try { await api.request(`/sessions/${answer.session_id}/questions/${answer.id}/feedback`, 'POST', { rating: value, notes }); setRating(value); }
    catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  return <article className="conversation-card"><div className="conversation-meta"><span>{new Date(answer.created_at).toLocaleString()} · {answer.language} · {answer.source}</span><span className={`pill ${answer.uncertain ? 'amber' : ''}`}>{answer.uncertain ? 'Uncertain' : 'Answered'}</span></div><h2>{answer.question}</h2><p dir="auto">{answer.answer}</p>{answer.processing_warnings?.map(w => <div className="notice error" key={w}>{w}</div>)}
    <div className="action-row"><button className="button" onClick={() => void play(`/sessions/${answer.session_id}/questions/${answer.id}/audio`).catch(e => setError(e.message))}>Play spoken answer</button><button className="button" onClick={stopSpeaking}>Stop audio</button></div>
    <div className="evidence"><span>{answer.evidence_frame_ids.length} supporting images</span>{answer.evidence_frame_ids.map((id, index) => <button className="text-link" key={id} onClick={() => void api.request(`/sessions/${answer.session_id}/frames/${id}`).then(onFrame).catch(e => setError(e.message))}>View evidence {index + 1}</button>)}</div>
    <label className="feedback-notes">Feedback notes (optional)<input value={notes} onChange={event => setNotes(event.target.value)} maxLength={2000} /></label><div className="action-row">{['correct', 'incorrect', 'unsure'].map(value => <button className={`button ${rating === value ? 'primary' : ''}`} key={value} disabled={busy} onClick={() => void feedback(value)}>{rating === value ? '✓ ' : ''}{value}</button>)}</div>
  </article>;
}
export default function Conversations({ onFrame }) {
  const { selectedId, questions, questionMore, loadMore, setError } = useDashboard();
  const [query, setQuery] = useState('');
  const [language, setLanguage] = useState('All languages');
  const [busy, setBusy] = useState(false);
  const found = questions.filter(answer => (language === 'All languages' || answer.language === language) && `${answer.question} ${answer.answer}`.toLowerCase().includes(query.toLowerCase()));
  return <><Heading title="Every question has a story." subtitle="Ask by text or voice, review shared answers, and inspect their evidence." />
    <QuestionComposer key={selectedId} /><div className="toolbar"><SearchInput value={query} onChange={setQuery} label="Search loaded conversations" placeholder="Find a question or answer…" /><Select label="Filter conversation language" value={language} onChange={setLanguage} options={['All languages', 'en', 'fr', 'ar']} /></div>
    {found.map(answer => <AnswerCard key={answer.id} answer={answer} onFrame={onFrame} />)}{!found.length && <div className="panel empty">No conversations match this view.</div>}
    {questionMore && <button className="button" disabled={busy} onClick={() => { setBusy(true); void loadMore('questions').catch(e => setError(e.message)).finally(() => setBusy(false)); }}>Load older conversations</button>}
  </>;
}

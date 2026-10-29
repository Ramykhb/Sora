import { useState } from 'react';
import FrameCard from '../components/FrameCard.jsx';
import { Heading, SearchInput } from '../components/Shared.jsx';
import { useDashboard } from '../providers/Dashboard.jsx';
export default function FrameLibrary({ onFrame }) {
  const { api, selectedId, frames, frameMore, loadMore, refreshData, setError } = useDashboard();
  const [query, setQuery] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [view, setView] = useState(null);
  const [busy, setBusy] = useState(false);
  function bounds() {
    const params = new URLSearchParams();
    if (since) params.set('since', new Date(since).toISOString());
    if (until) params.set('until', new Date(until).toISOString());
    return params;
  }
  async function run(work) {
    setBusy(true); setError('');
    try { await work(); } catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  async function search(event) {
    event.preventDefault();
    await run(async () => {
      const params = bounds(); params.set('q', query.trim()); params.set('limit', '10');
      const response = await api.request(`/sessions/${selectedId}/frames/search?${params}`);
      setView({ kind: 'search', frames: response.frames, more: false });
      if (response.warnings.length) setError(response.warnings.join('\n'));
    });
  }
  async function timeline(append = false) {
    if (!since && !until && !append) { setView(null); setQuery(''); await refreshData(); return; }
    const params = append ? new URLSearchParams(view.params) : bounds();
    params.set('limit', '50'); params.set('offset', append ? String(view.frames.length) : '0');
    const response = await api.request(`/sessions/${selectedId}/frames?${params}`);
    setView(previous => ({ kind: 'timeline', params: params.toString(), frames: append ? [...new Map([...previous.frames, ...response].map(frame => [frame.id, frame])).values()] : response, more: response.length === 50 }));
  }
  const shown = view?.frames || frames;
  return <><Heading title="A memory you can explore." subtitle="Authenticated images, OCR and object detections from the selected mobile session." />
    <form onSubmit={search} className="toolbar"><SearchInput value={query} onChange={setQuery} label="Search visual memory" placeholder="Search scenes, objects or recognized text…" /><label>Since<input type="datetime-local" value={since} onChange={e => setSince(e.target.value)} /></label><label>Until<input type="datetime-local" value={until} onChange={e => setUntil(e.target.value)} /></label><button className="button primary" disabled={!selectedId || busy || !query.trim()}>Search memory</button><button type="button" className="button" disabled={busy || !selectedId} onClick={() => void run(() => timeline())}>Show timeline</button></form>
    <p className="muted">{shown.length} loaded moments{view?.kind === 'search' && ' · semantic search results'}</p><div className="frames large-frames">{shown.map(frame => <FrameCard key={frame.id} frame={frame} onSelect={selected => onFrame(selected, id => setView(previous => previous ? { ...previous, frames: previous.frames.filter(item => item.id !== id) } : null))} />)}</div>
    {!shown.length && <div className="panel empty">No retained images match this view.</div>}{(view ? view.more : frameMore) && <button className="button" disabled={busy} onClick={() => void run(() => view ? timeline(true) : loadMore('frames'))}>Load more images</button>}
  </>;
}

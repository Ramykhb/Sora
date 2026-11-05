import { useState } from 'react';
import { useDashboard } from '../providers/Dashboard.jsx';
export default function SessionActions() {
  const { api, session, selectedId, status, refreshData, refreshSessions, setError } = useDashboard();
  const [busy, setBusy] = useState(false);
  async function close() {
    if (!window.confirm('End mobile capture for this session? Its retained memory will remain until expiry.')) return;
    setBusy(true);
    try { await api.request(`/sessions/${selectedId}/close`, 'POST'); await Promise.all([refreshData(), refreshSessions()]); }
    catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  return <><span className={`session-badge ${status?.streaming ? 'online' : ''}`}><i />{status?.streaming ? 'Live session' : session ? session.status === 'active' ? 'Waiting for camera' : 'Session ended' : 'No session'}</span><button className="button end-session" disabled={!selectedId || session?.status !== 'active' || busy} onClick={() => void close()}>{busy ? 'Ending…' : 'End session'}</button></>;
}

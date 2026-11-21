import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
import { useAuth } from '@/providers/auth';
import { Action, Field } from './controls';
import { Card, Label } from './sora-ui';

type Watch = { id: string; target: string; expires_at: string };

export function DetectionWatchSettings() {
  const { tokens } = useAuth();
  const [expanded, setExpanded] = useState(false);
  if (!tokens) return null;
  return <Card><Action title={expanded ? 'Hide pending alerts' : 'Manage pending alerts'} onPress={() => setExpanded(value => !value)} />{expanded && <WatchList key={tokens.user.id} />}</Card>;
}

function WatchList() {
  const { api, tokens, serverUrl } = useAuth();
  const owner = tokens?.user.id;
  const [watches, setWatches] = useState<Watch[]>([]);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [target, setTarget] = useState('');
  const mounted = useRef(true);
  const lock = useRef(false);
  const current = () => mounted.current && api.tokens?.user.id === owner && api.baseUrl === serverUrl;
  async function refresh() {
    const rows = await api.request<Watch[]>('/detection-watches');
    if (current()) setWatches(rows);
  }
  async function run(work: () => Promise<void>) {
    if (lock.current || !current()) return;
    lock.current = true; setBusy(true); setMessage('');
    try { await work(); }
    catch (error) { if (current()) setMessage(error instanceof Error ? error.message : 'Unable to manage pending alerts.'); }
    finally { lock.current = false; if (current()) setBusy(false); }
  }
  useEffect(() => {
    mounted.current = true;
    void api.request<Watch[]>('/detection-watches').then(rows => { if (current()) setWatches(rows); }).catch(error => { if (current()) setMessage(error.message); }).finally(() => { if (current()) setBusy(false); });
    return () => { mounted.current = false; };
    // This list is remounted when opened and when its account changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <View style={{ gap: 10 }}>
    <Label bold>Pending detection requests</Label>
    <Label muted size={12}>Requests expire automatically. Editing preserves the expiry time. Cancel requests you no longer need.</Label>
    <Action title="Refresh pending alerts" disabled={busy} onPress={() => void run(refresh)} />
    {!busy && !watches.length && <Label>No pending alerts.</Label>}
    {watches.map(watch => <View key={watch.id} style={{ gap: 8 }}>
      <Label bold>{watch.target}</Label><Label muted size={12}>Expires {new Date(watch.expires_at).toLocaleString()}</Label>
      <Action title={`Edit alert for ${watch.target}`} disabled={busy} onPress={() => { setEditing(watch.id); setTarget(watch.target); }} />
      <Action title={`Cancel alert for ${watch.target}`} variant="danger" disabled={busy} onPress={() => void run(async () => { await api.request(`/detection-watches/${watch.id}`, 'DELETE'); if (current()) { setEditing(null); await refresh(); } })} />
    </View>)}
    {editing && <><Field accessibilityLabel="Object or sign to watch for" value={target} onChangeText={setTarget} maxLength={200} editable={!busy} />
      <Action title="Save alert changes" disabled={busy || !target.trim()} onPress={() => void run(async () => { await api.request(`/detection-watches/${editing}`, 'PUT', { target }); if (current()) { setEditing(null); await refresh(); } })} />
      <Action title="Cancel editing alert" disabled={busy} onPress={() => setEditing(null)} /></>}
    {!!watches.length && <Action title="Cancel all pending alerts" variant="danger" disabled={busy} onPress={() => void run(async () => { await api.request('/detection-watches', 'DELETE'); if (current()) { setEditing(null); await refresh(); } })} />}
    {!!message && <Label accessibilityRole="alert">{message}</Label>}
  </View>;
}

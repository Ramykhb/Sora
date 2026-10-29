import { useEffect, useState } from 'react';
import { Text } from 'react-native';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/providers/auth';
import { ui } from './controls';
type Status = { streaming: boolean; frames_received?: number; frames_stored?: number; frames_rejected?: number; frames_dropped?: number; processing_error?: string };
export function StreamStatus({ sessionId, onUnavailable }: { sessionId: string; onUnavailable: (error: unknown) => void }) {
  const { api } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function update() {
      try {
        const value = await api.request<Status>(`/sessions/${sessionId}/stream/status`);
        if (!cancelled) { setStatus(value); setError(''); }
      } catch (e) { if (!cancelled) { setError(e instanceof Error ? e.message : 'Status unavailable'); if (e instanceof ApiError && e.status === 404) onUnavailable(e); } }
      finally { if (!cancelled) timer = setTimeout(() => void update(), 5000); }
    }
    void update();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [api, sessionId, onUnavailable]);
  return <>{error ? <Text style={ui.error}>{error}</Text> : status?.streaming ? <Text style={ui.copy}>Received {status.frames_received} · saved {status.frames_stored} · skipped {status.frames_rejected} · dropped {status.frames_dropped}</Text> : <Text style={ui.copy}>Waiting for camera frames</Text>}{!!status?.processing_error && <Text style={ui.error}>{status.processing_error}</Text>}</>;
}

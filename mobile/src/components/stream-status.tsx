import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import { Card, Icon, Label } from './sora-ui';
type Status = { streaming: boolean; frames_received?: number; frames_sampled?: number; frames_stored?: number; frames_rejected?: number; frames_dropped?: number; processing_error?: string; detection_error?: string };
export function StreamStatus({ sessionId, onUnavailable }: { sessionId: string; onUnavailable: (error: unknown) => void }) {
  const { colors } = usePreferences();
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
  return <Card style={{ gap: 16 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><Icon name="pulse-outline" color={status?.streaming ? colors.success : colors.muted} size={18} /><Label bold size={13}>Live status</Label><Label muted size={10} style={{ marginLeft: 'auto' }}>{status?.streaming ? 'RECEIVING' : 'WAITING'}</Label></View>{error ? <Label accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Label> : status?.streaming ? <View style={{ flexDirection: 'row', gap: 8 }}>{[{ label: 'Received', value: status.frames_received }, { label: 'Sampled', value: status.frames_sampled }, { label: 'Saved', value: status.frames_stored }].map(metric => <View key={metric.label} style={{ flex: 1, backgroundColor: colors.elevated, borderRadius: 10, padding: 10, gap: 4 }}><Label bold size={23}>{metric.value ?? '—'}</Label><Label muted size={10}>{metric.label}</Label></View>)}</View> : <Label muted size={12}>Waiting for camera frames</Label>}{status?.streaming && <Label muted size={11}>Skipped {status.frames_rejected ?? 0} · Dropped {status.frames_dropped ?? 0}</Label>}{!!status?.processing_error && <Label accessibilityRole="alert" style={{ color: colors.danger }}>{status.processing_error}</Label>}{!!status?.detection_error && <Label accessibilityRole="alert" style={{ color: colors.danger }}>Live detection unavailable: {status.detection_error}</Label>}</Card>;
}

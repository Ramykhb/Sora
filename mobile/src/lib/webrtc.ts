import { ApiClient } from './api';

export type StreamConfig = { ice_servers: RTCIceServer[]; ice_transport_policy: 'all' | 'relay' };
type SignalingPeer = {
  iceGatheringState: string;
  localDescription: { sdp: string; type: string | null } | null;
  createOffer(): Promise<{ sdp?: string; type: string | null }>;
  setLocalDescription(description: { type: 'offer'; sdp: string }): Promise<void>;
  setRemoteDescription(description: { type: 'answer'; sdp: string }): Promise<void>;
  addEventListener(type: 'icegatheringstatechange', listener: () => void): void;
  removeEventListener(type: 'icegatheringstatechange', listener: () => void): void;
};

export function waitForIce(peer: SignalingPeer, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const finish = (error?: Error) => {
      clearTimeout(timeout); peer.removeEventListener('icegatheringstatechange', changed);
      signal.removeEventListener('abort', aborted);
      if (error) reject(error); else resolve();
    };
    const changed = () => { if (peer.iceGatheringState === 'complete') finish(); };
    const aborted = () => finish(new Error('Camera connection cancelled'));
    const timeout = setTimeout(() => finish(new Error('WebRTC could not gather candidates. Check the TURN relay.')), 15000);
    peer.addEventListener('icegatheringstatechange', changed);
    signal.addEventListener('abort', aborted, { once: true });
    if (signal.aborted) aborted(); else changed();
  });
}

export async function publishVideo(api: ApiClient, sessionId: string, peer: SignalingPeer, signal: AbortSignal) {
  const offer = await peer.createOffer();
  if (!offer.sdp) throw new Error('Camera did not create a video offer');
  await peer.setLocalDescription({ type: 'offer', sdp: offer.sdp });
  await waitForIce(peer, signal);
  const answer = await api.request<{ type: 'answer'; sdp: string; connection_id: string }>(
    `/sessions/${sessionId}/stream/offer`, 'POST', { type: 'offer', sdp: peer.localDescription?.sdp },
  );
  try {
    if (signal.aborted) throw new Error('Camera connection cancelled');
    await peer.setRemoteDescription({ type: 'answer', sdp: answer.sdp });
  } catch (error) {
    void api.request(`/sessions/${sessionId}/stream/connections/${answer.connection_id}`, 'DELETE').catch(() => {});
    throw error;
  }
  return answer.connection_id;
}

export function maintainVideo(api: ApiClient, sessionId: string, connectionId: string, onError: (error: unknown) => void) {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout>;
  async function refresh() {
    try {
      await api.request(`/sessions/${sessionId}/stream/connections/${connectionId}/refresh`, 'POST');
      if (!stopped) timer = setTimeout(() => void refresh(), 20000);
    } catch (error) { if (!stopped) onError(error); }
  }
  timer = setTimeout(() => void refresh(), 20000);
  return () => {
    stopped = true; clearTimeout(timer);
    if (api.tokens) void api.request(`/sessions/${sessionId}/stream/connections/${connectionId}`, 'DELETE').catch(() => {});
  };
}

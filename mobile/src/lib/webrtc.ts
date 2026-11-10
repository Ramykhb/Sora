import { ApiClient, ApiError, isTransientNetworkError } from './api';

export type StreamConfig = { ice_servers: RTCIceServer[]; ice_transport_policy: 'all' | 'relay' };
type SignalingPeer = {
  iceGatheringState: string;
  localDescription: { sdp: string; type: string | null } | null;
  createOffer(): Promise<{ sdp?: string; type: string | null }>;
  setLocalDescription(description: { type: 'offer'; sdp: string }): Promise<void>;
  setRemoteDescription(description: { type: 'answer'; sdp: string }): Promise<void>;
  addEventListener(type: 'icegatheringstatechange' | 'icecandidate', listener: () => void): void;
  removeEventListener(type: 'icegatheringstatechange' | 'icecandidate', listener: () => void): void;
};

// Shared capture/encoding budget for native and browser publishers. Keep this in
// JavaScript so an existing WebRTC development client can load it through Metro.
export const VIDEO_CAPTURE = { width: 1280, height: 720, frameRate: 60 };
export const VIDEO_MAX_BITRATE = 6_000_000;

export async function videoDiagnostics(peer: { getStats(): Promise<{ forEach(callback: (value: unknown) => void): void }> }) {
  const stats = await peer.getStats();
  const fields = ['type', 'kind', 'mediaType', 'framesPerSecond', 'frameWidth', 'frameHeight',
    'framesEncoded', 'framesSent', 'frames', 'width', 'height', 'qualityLimitationReason',
    'totalEncodeTime', 'bytesSent', 'packetsSent', 'targetBitrate', 'encoderImplementation',
    'currentRoundTripTime', 'availableOutgoingBitrate', 'state', 'mimeType'];
  const reports: Record<string, unknown>[] = [];
  stats.forEach(value => {
    const report = value as Record<string, unknown>;
    if (!['outbound-rtp', 'media-source', 'candidate-pair', 'codec'].includes(String(report.type))) return;
    if (report.kind === 'audio' || report.mediaType === 'audio') return;
    if (report.type === 'candidate-pair' && report.state !== 'succeeded') return;
    reports.push(Object.fromEntries(fields.filter(key => report[key] !== undefined).map(key => [key, report[key]])));
  });
  return { profile: '720p60-v3', capture: VIDEO_CAPTURE, reports };
}

type VideoSendParameters = {
  encodings: { maxBitrate?: number | null; maxFramerate?: number | null; scaleResolutionDownBy?: number | null }[];
  degradationPreference?: string | null;
};

export async function configureVideoSender<T extends VideoSendParameters>(sender: {
  getParameters(): T;
  setParameters(parameters: T): Promise<void>;
}) {
  // Call after negotiation, when encodings exist. Preserve native parameter
  // objects (including their setters/toJSON), transaction ID and encoding count.
  const parameters = sender.getParameters();
  // Leave the negotiated adaptation policy intact. react-native-webrtc 155 on
  // iOS serializes this enum differently from its JS wrapper; writing it can
  // break the setParameters round trip and restart an otherwise healthy stream.
  for (const encoding of parameters.encodings) {
    encoding.maxBitrate = VIDEO_MAX_BITRATE;
    encoding.maxFramerate = VIDEO_CAPTURE.frameRate;
    encoding.scaleResolutionDownBy = 1;
  }
  await sender.setParameters(parameters);
}

export function waitForIce(peer: SignalingPeer, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    let settled = false;
    let relayReady: ReturnType<typeof setTimeout> | undefined;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(relayReady);
      clearTimeout(timeout); peer.removeEventListener('icegatheringstatechange', changed);
      peer.removeEventListener('icecandidate', changed);
      signal.removeEventListener('abort', aborted);
      if (error) reject(error); else resolve();
    };
    const changed = () => {
      if (peer.iceGatheringState === 'complete') { finish(); return; }
      // A TURN candidate is sufficient for this single-offer exchange. Cellular
      // interfaces can keep gathering long after the Wi-Fi relay is ready.
      if (!relayReady && /^a=candidate:.*\btyp relay\b/m.test(peer.localDescription?.sdp || '')) {
        relayReady = setTimeout(() => finish(), 1000);
      }
    };
    const aborted = () => finish(new Error('Camera connection cancelled'));
    const timeout = setTimeout(() => {
      if (/^a=candidate:/m.test(peer.localDescription?.sdp || '')) finish();
      else finish(new Error('WebRTC could not gather candidates. Check the TURN relay.'));
    }, 15000);
    peer.addEventListener('icegatheringstatechange', changed);
    peer.addEventListener('icecandidate', changed);
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

export function maintainVideo(api: ApiClient, sessionId: string, connectionId: string, onError: (error: unknown) => void, diagnostics?: () => Promise<unknown>) {
  let stopped = false;
  let failures = 0;
  let timer: ReturnType<typeof setTimeout>;
  async function refresh() {
    try {
      const video_metrics = await diagnostics?.().catch(() => null);
      if (stopped) return;
      await api.request(`/sessions/${sessionId}/stream/connections/${connectionId}/refresh`, 'POST', video_metrics ? { video_metrics } : undefined);
      failures = 0;
      if (!stopped) timer = setTimeout(() => void refresh(), 20000);
    } catch (error) {
      if (stopped) return;
      const transient = isTransientNetworkError(error) ||
        (error instanceof ApiError && (error.status === 408 || error.status >= 500));
      // A lost HTTP heartbeat does not mean the WebRTC video has disconnected.
      // Keep media running during a short retry window; authorization/closed
      // connection errors still stop immediately.
      if (transient && ++failures < 3) {
        timer = setTimeout(() => void refresh(), 1000 * 2 ** (failures - 1));
      } else onError(error);
    }
  }
  timer = setTimeout(() => void refresh(), diagnostics ? 5000 : 20000);
  return () => {
    stopped = true; clearTimeout(timer);
    if (api.tokens) void api.request(`/sessions/${sessionId}/stream/connections/${connectionId}`, 'DELETE').catch(() => {});
  };
}

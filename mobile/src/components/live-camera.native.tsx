import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import type * as NativeRTC from 'react-native-webrtc';
import { useAuth } from '@/providers/auth';
import { maintainVideo, publishVideo, type StreamConfig } from '@/lib/webrtc';
import { ui } from './controls';

export function LiveCamera({ sessionId, active }: { sessionId: string; active: boolean }) {
  const { api } = useAuth();
  const [rtc] = useState(() => {
    // Older development binaries can render the rebuild message without crashing.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    try { return require('react-native-webrtc') as typeof NativeRTC; }
    catch { return null; }
  });
  const [stream, setStream] = useState<NativeRTC.MediaStream | null>(null);
  const [status, setStatus] = useState('Connecting video…');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!active || !rtc) return;
    let disposed = false;
    let media: NativeRTC.MediaStream | undefined;
    let peer: NativeRTC.RTCPeerConnection | undefined;
    let release: (() => void) | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const fail = (error: unknown) => {
      if (disposed || retry) return;
      setStatus(error instanceof Error ? error.message : 'Video disconnected. Reconnecting…');
      retry = setTimeout(() => setAttempt(value => value + 1), 3000);
      controller.abort(); clearTimeout(watchdog);
      media?.getTracks().forEach(track => track.stop());
      peer?.close(); release?.(); release = undefined;
    };
    const watchdog = setTimeout(() => fail(new Error('Video connection timed out. Check the TURN relay.')), 30000);
    async function connect() {
      setStatus('Connecting WebRTC video…');
      try {
        const config = await api.request<StreamConfig>(`/sessions/${sessionId}/stream/config`);
        if (disposed) return;
        media = await rtc!.mediaDevices.getUserMedia({ audio: false, video: { facingMode: 'environment', width: 1280, height: 720, frameRate: 15 } });
        if (disposed) { media.getTracks().forEach(track => track.stop()); return; }
        setStream(media);
        peer = new rtc!.RTCPeerConnection({ iceServers: config.ice_servers, iceTransportPolicy: config.ice_transport_policy });
        media.getTracks().forEach(track => peer!.addTrack(track, media!));
        peer.addEventListener('connectionstatechange', () => {
          if (disposed) return;
          if (peer?.connectionState === 'connected') { clearTimeout(watchdog); setStatus('Streaming live video'); }
          if (peer && ['failed', 'closed'].includes(peer.connectionState)) fail(new Error('Video connection failed. Reconnecting…'));
        });
        const id = await publishVideo(api, sessionId, peer, controller.signal);
        release = maintainVideo(api, sessionId, id, fail);
        if (disposed) { release(); release = undefined; }
      } catch (error) { fail(error); }
    }
    void connect();
    return () => {
      disposed = true; controller.abort(); clearTimeout(retry); clearTimeout(watchdog);
      release?.(); peer?.close(); media?.getTracks().forEach(track => track.stop()); setStream(null);
    };
  }, [active, api, rtc, sessionId, attempt]);
  const Video = rtc?.RTCView;
  return <View style={ui.card}>
    <Text style={ui.subtitle}>{!rtc ? 'Rebuild the development app to enable WebRTC video.' : active ? status : 'Camera paused'}</Text>
    {active && Video && stream && <Video streamURL={stream.toURL()} objectFit="cover" style={{ height: 240, borderRadius: 16 }} />}
  </View>;
}

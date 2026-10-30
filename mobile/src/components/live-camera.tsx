import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { useAuth } from '@/providers/auth';
import { maintainVideo, publishVideo, type StreamConfig } from '@/lib/webrtc';
import { ui } from './controls';

export function LiveCamera({ sessionId, active }: { sessionId: string; active: boolean }) {
  const { api } = useAuth();
  const video = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState('Connecting video…');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!active) return;
    let disposed = false;
    let media: MediaStream | undefined;
    let peer: RTCPeerConnection | undefined;
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
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('Browser camera streaming requires HTTPS or localhost.');
        media = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 15, max: 15 } } });
        if (disposed) { media.getTracks().forEach(track => track.stop()); return; }
        if (video.current) { video.current.srcObject = media; await video.current.play(); }
        peer = new RTCPeerConnection({ iceServers: config.ice_servers, iceTransportPolicy: config.ice_transport_policy });
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
      release?.(); peer?.close(); media?.getTracks().forEach(track => track.stop());
    };
  }, [active, api, sessionId, attempt]);
  return <View style={ui.card}><Text style={ui.subtitle}>{active ? status : 'Camera paused'}</Text>
    {active && <video ref={video} autoPlay muted playsInline style={{ width: '100%', height: 240, objectFit: 'cover', borderRadius: 16 }} />}
  </View>;
}

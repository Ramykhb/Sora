import { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { useAuth } from '@/providers/auth';
import { configureVideoSender, maintainVideo, publishVideo, videoDiagnostics, VIDEO_CAPTURE, type StreamConfig } from '@/lib/webrtc';
import { useUI } from './controls';

export function LiveCamera({ sessionId, active, fullscreen = false, facing = 'back', onConnectionChange }: { sessionId: string; active: boolean; fullscreen?: boolean; facing?: 'back' | 'front'; onConnectionChange?: (connected: boolean) => void }) {
  const ui = useUI();
  const { api } = useAuth();
  const video = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState('Connecting video…');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { onConnectionChange?.(active && status === 'Streaming live video'); }, [active, status, onConnectionChange]);
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
        media = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: facing === 'back' ? 'environment' : 'user', width: { ideal: VIDEO_CAPTURE.width }, height: { ideal: VIDEO_CAPTURE.height }, frameRate: { ideal: VIDEO_CAPTURE.frameRate, max: VIDEO_CAPTURE.frameRate } } });
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
        release = maintainVideo(api, sessionId, id, fail, () => videoDiagnostics(peer!));
        const sender = peer.getSenders().find(sender => sender.track?.kind === 'video');
        if (sender && !disposed) await configureVideoSender(sender);
        if (disposed) { release(); release = undefined; }
      } catch (error) { fail(error); }
    }
    void connect();
    return () => {
      disposed = true; controller.abort(); clearTimeout(retry); clearTimeout(watchdog);
      release?.(); peer?.close(); media?.getTracks().forEach(track => track.stop());
    };
  }, [active, api, sessionId, attempt, facing]);
  return <View style={fullscreen ? { position: 'absolute', top: 0, bottom: 0, left: 0, right: 0 } : ui.card}>{(!fullscreen || status !== 'Streaming live video') && <Text accessibilityLiveRegion="polite" style={fullscreen ? { position: 'absolute', top: 115, left: 22, right: 22, zIndex: 2, color: ui.subtitle.color, backgroundColor: ui.card.backgroundColor, padding: 10, borderRadius: 12 } : ui.subtitle}>{active ? status : 'Camera paused'}</Text>}
    {active && <video ref={video} autoPlay muted playsInline style={{ width: '100%', height: fullscreen ? '100%' : 240, objectFit: 'contain', borderRadius: fullscreen ? 0 : 16 }} />}
  </View>;
}

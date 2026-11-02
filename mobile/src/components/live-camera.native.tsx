import { useEffect, useState } from 'react';
import { NativeModules, Text, View } from 'react-native';
import type * as NativeRTC from 'react-native-webrtc';
import { useAuth } from '@/providers/auth';
import { maintainVideo, publishVideo, type StreamConfig } from '@/lib/webrtc';
import { useUI } from './controls';

export function LiveCamera({ sessionId, active, fullscreen = false, facing = 'back', onConnectionChange }: { sessionId: string; active: boolean; fullscreen?: boolean; facing?: 'back' | 'front'; onConnectionChange?: (connected: boolean) => void }) {
  const ui = useUI();
  const { api } = useAuth();
  const [rtc] = useState(() => {
    // Check before importing: WebRTC creates a native event emitter at import time.
    // Catching the import error still lets Metro report it in Expo Go/older binaries.
    if (!NativeModules.WebRTCModule) return null;
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    try { return require('react-native-webrtc') as typeof NativeRTC; }
    catch { return null; }
  });
  const [stream, setStream] = useState<NativeRTC.MediaStream | null>(null);
  const [status, setStatus] = useState('Connecting video…');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { onConnectionChange?.(active && status === 'Streaming live video'); }, [active, status, onConnectionChange]);
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
        media = await rtc!.mediaDevices.getUserMedia({ audio: false, video: { facingMode: facing === 'back' ? 'environment' : 'user', width: 1280, height: 720, frameRate: 15 } });
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
  }, [active, api, rtc, sessionId, attempt, facing]);
  const Video = rtc?.RTCView;
  return <View style={fullscreen ? { position: 'absolute', top: 0, bottom: 0, left: 0, right: 0 } : ui.card}>
    {(!fullscreen || !rtc || status !== 'Streaming live video') && <Text accessibilityLiveRegion="polite" style={fullscreen ? { position: 'absolute', top: 115, left: 22, right: 22, zIndex: 2, color: 'white', backgroundColor: '#080D1699', padding: 10, borderRadius: 10 } : ui.subtitle}>{!rtc ? 'Live video requires a development build with WebRTC. Install the rebuilt app instead of opening Expo Go.' : active ? status : 'Camera paused'}</Text>}
    {active && Video && stream && <Video streamURL={stream.toURL()} objectFit="cover" style={fullscreen ? { flex: 1 } : { height: 240, borderRadius: 16 }} />}
  </View>;
}

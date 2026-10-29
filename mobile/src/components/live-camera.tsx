import { CameraView, useCameraPermissions } from 'expo-camera';
import { useEffect, useRef, useState } from 'react';
import { Platform, Text, View } from 'react-native';
import { File } from 'expo-file-system';
import { useAuth } from '@/providers/auth';
import { connectLive, jpegBytes } from '@/lib/live';
import { Action, ui } from './controls';

export function LiveCamera({ sessionId, active }: { sessionId: string; active: boolean }) {
  const { api } = useAuth();
  const camera = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [cameraReady, setCameraReady] = useState(false);
  const [status, setStatus] = useState('Paused');
  useEffect(() => {
    if (!active || !cameraReady || !permission?.granted) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const live = connectLive(api, `/sessions/${sessionId}/stream/frames`, () => {}, setStatus);
    async function capture() {
      try {
        if (live.ready) {
          const picture = await camera.current?.takePictureAsync({ quality: 0.35, base64: true, shutterSound: false });
          try {
            if (!cancelled && picture?.base64) live.send(jpegBytes(picture.base64));
          } finally {
            if (picture?.uri && Platform.OS !== 'web') new File(picture.uri).delete();
          }
        }
      } catch (e) { if (!cancelled) setStatus(e instanceof Error ? e.message : 'Camera capture failed'); }
      finally { if (!cancelled) timer = setTimeout(() => void capture(), 250); }
    }
    void capture();
    return () => { cancelled = true; clearTimeout(timer); live.close(); };
  }, [active, api, cameraReady, permission?.granted, sessionId]);
  return <View style={ui.card}>
    <Text style={ui.subtitle}>{active ? status : 'Camera paused'}</Text>
    {!permission?.granted ? <Action title={permission?.canAskAgain === false ? 'Camera denied — enable access in device settings' : 'Allow camera access'} onPress={() => void requestPermission()} /> : active ? <CameraView ref={camera} facing="back" style={{ height: 240, borderRadius: 16 }} onCameraReady={() => setCameraReady(true)} onMountError={e => setStatus(e.message)} /> : <Text style={ui.copy}>Resume assistance to share your camera view.</Text>}
  </View>;
}

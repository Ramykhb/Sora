import { ApiClient, type LiveEvent } from './api';

// Decode on all three platforms; only binary JPEG bytes travel over the socket.
export function jpegBytes(base64: string): ArrayBuffer {
  const text = atob(base64.replace(/^data:image\/[^;]+;base64,/, ''));
  return Uint8Array.from(text, char => char.charCodeAt(0)).buffer;
}

export function connectLive(api: ApiClient, path: string, onEvent: (event: LiveEvent) => void, onStatus: (status: string) => void) {
  let disposed = false;
  let socket: WebSocket | null = null;
  let ready = false;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let rotate: ReturnType<typeof setTimeout> | undefined;
  let attempts = 0;
  async function connect() {
    if (disposed) return;
    onStatus('Connecting…');
    try {
      const token = await api.token();
      if (disposed) return;
      const ws = new WebSocket(api.url(path).replace(/^http/, 'ws'));
      socket = ws;
      let handshake = setTimeout(() => ws.close(), 10000);
      ws.onopen = () => ws.send(JSON.stringify({ access_token: token }));
      ws.onmessage = message => {
        if (disposed || socket !== ws) return;
        try {
          const event: LiveEvent = JSON.parse(message.data);
          if (event.type === 'ready') {
            clearTimeout(handshake); ready = true; attempts = 0; onStatus('Connected');
            // HTTP and sockets share the rotated token. Reconnect before its expiry.
            rotate = setTimeout(() => ws.close(), Math.max(1000, ((api.tokens?.expires_in || 300) - 40) * 1000));
          }
          if (event.type === 'error') onStatus(event.code || 'Stream error');
          onEvent(event);
        } catch { onStatus('Invalid live response'); }
      };
      ws.onerror = () => onStatus('Connection interrupted');
      ws.onclose = () => {
        clearTimeout(handshake); clearTimeout(rotate); ready = false;
        if (!disposed) {
          onStatus('Reconnecting…');
          retry = setTimeout(() => void connect(), Math.min(15000, 1000 * 2 ** attempts++));
        }
      };
    } catch (e) {
      if (!disposed) {
        onStatus(e instanceof Error ? e.message : 'Connection failed');
        retry = setTimeout(() => void connect(), 5000);
      }
    }
  }
  void connect();
  return {
    send(bytes: ArrayBuffer) {
      if (!ready || socket?.readyState !== WebSocket.OPEN || socket.bufferedAmount > 512000) return false;
      socket.send(bytes); return true;
    },
    get ready() { return ready; },
    close() { disposed = true; ready = false; clearTimeout(retry); clearTimeout(rotate); socket?.close(); },
  };
}

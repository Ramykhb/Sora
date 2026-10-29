// FastAPI sends multipart JPEG parts with Content-Length. Never decode JPEG bytes as text.
const encoder = new TextEncoder();
const separator = encoder.encode('\r\n\r\n');
function findBytes(buffer, needle) {
  outer: for (let i = 0; i <= buffer.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) if (buffer[i + j] !== needle[j]) continue outer;
    return i;
  }
  return -1;
}
export class MjpegParser {
  buffer = new Uint8Array();
  length = null;
  push(chunk) {
    const joined = new Uint8Array(this.buffer.length + chunk.length);
    joined.set(this.buffer); joined.set(chunk, this.buffer.length); this.buffer = joined;
    const frames = [];
    while (true) {
      if (this.length === null) {
        const end = findBytes(this.buffer, separator);
        if (end === -1) {
          if (this.buffer.length > 8192) throw new Error('Invalid live stream headers.');
          break;
        }
        const header = new TextDecoder().decode(this.buffer.subarray(0, end));
        const match = /Content-Length:\s*(\d+)/i.exec(header);
        if (!match || !/Content-Type:\s*image\/jpeg/i.test(header)) throw new Error('Unsupported live stream format.');
        this.length = Number(match[1]);
        if (this.length < 1 || this.length > 16 * 1024 * 1024) throw new Error('Live frame exceeds the size limit.');
        this.buffer = this.buffer.slice(end + 4);
      }
      if (this.buffer.length < this.length) break;
      frames.push(this.buffer.slice(0, this.length));
      this.buffer = this.buffer.slice(this.length); this.length = null;
    }
    return frames;
  }
}

export function subscribeEvents(api, sessionId, onEvent, onStatus) {
  let stopped = false;
  let socket;
  let timer;
  let handshake;
  let retry = 1000;
  async function connect() {
    if (stopped) return;
    onStatus('Connecting');
    try {
      const token = await api.token();
      if (stopped) return;
      socket = new WebSocket(api.socketUrl(`/sessions/${sessionId}/events`));
      handshake = setTimeout(() => socket.close(), 15000);
      socket.onopen = () => socket.send(JSON.stringify({ access_token: token }));
      socket.onmessage = message => {
        if (stopped) return;
        try {
          const event = JSON.parse(message.data);
          clearTimeout(handshake); handshake = setTimeout(() => socket.close(), 25000);
          if (event.type === 'ready' || event.type === 'heartbeat') { retry = 1000; onStatus('Connected'); }
          onEvent(event);
        } catch { onStatus('Invalid event response'); }
      };
      socket.onerror = () => onStatus('Connection interrupted');
      socket.onclose = () => { clearTimeout(handshake); schedule(); };
    } catch (error) { if (!stopped) { onStatus(error.message); schedule(); } }
  }
  function schedule() {
    if (stopped) return;
    onStatus('Reconnecting'); timer = setTimeout(() => void connect(), retry); retry = Math.min(15000, retry * 2);
  }
  void connect();
  return () => { stopped = true; clearTimeout(timer); clearTimeout(handshake); socket?.close(); };
}

export function chooseSession(sessions, currentId, followLive) {
  const current = sessions.find(item => item.id === currentId);
  if (!followLive && current) return current.id;
  return sessions.find(item => item.live?.streaming)?.id || current?.id || sessions.find(item => item.status === 'active')?.id || sessions[0]?.id || '';
}

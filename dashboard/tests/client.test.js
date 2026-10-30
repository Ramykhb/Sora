import { afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { ApiClient, ApiError } from '../src/lib/api.js';
import { chooseSession, MjpegParser, subscribeEvents } from '../src/lib/live.js';
import { loadDashboard } from '../src/lib/dashboard.js';
import { subscribeVideo } from '../src/lib/webrtc.js';
const originalFetch = globalThis.fetch;
const originalSocket = globalThis.WebSocket;
const originalPeer = globalThis.RTCPeerConnection;
afterEach(() => { globalThis.fetch = originalFetch; globalThis.WebSocket = originalSocket; globalThis.RTCPeerConnection = originalPeer; });
const pair = (access = 'access') => ({ access_token: access, refresh_token: `refresh-${access}`, expires_in: 300, user: { id: 'owner' } });
const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

test('dashboard negotiates a receive-only WebRTC viewer and releases only its connection', async () => {
  let peer;
  class Peer {
    iceGatheringState = 'complete';
    constructor() { peer = this; }
    addTransceiver(kind, options) { assert.equal(kind, 'video'); assert.equal(options.direction, 'recvonly'); }
    async createOffer() { return { type: 'offer', sdp: 'viewer video SDP' }; }
    async setLocalDescription(offer) { this.localDescription = offer; }
    async setRemoteDescription(answer) { this.answer = answer; }
    addEventListener() {} removeEventListener() {}
    close() { this.closed = true; }
  }
  globalThis.RTCPeerConnection = Peer;
  const requests = [];
  const api = { tokens: pair(), async request(path, method, body) {
    requests.push({ path, method, body });
    if (path.endsWith('/config')) return { ice_servers: [], ice_transport_policy: 'all' };
    return { type: 'answer', sdp: 'relayed video SDP', connection_id: 'viewer-id' };
  } };
  const streams = [];
  const stop = subscribeVideo(api, 'phone', stream => streams.push(stream), () => {});
  try {
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(peer.answer.sdp, 'relayed video SDP');
    const stream = { id: 'continuous-video' };
    peer.ontrack({ streams: [stream], track: {} });
    assert.equal(streams.at(-1), stream);
    assert.equal(requests[1].path, '/sessions/phone/stream/viewer/offer');
    assert.ok(!requests.some(item => /preview.jpg|live.mjpeg/.test(item.path)));
  } finally { stop(); }
  assert.equal(peer.closed, true);
  assert.equal(requests.at(-1).path, '/sessions/phone/stream/connections/viewer-id');
  assert.equal(requests.at(-1).method, 'DELETE');
});

test('session discovery survives a failed statistics request and preserves account isolation', async () => {
  const api = { request: async path => {
    if (path === '/dashboard/statistics?own_only=true') throw new TypeError('Load failed');
    if (path.startsWith('/dashboard')) return { sessions: [{ session_id: 'phone', live: { streaming: true } }] };
    return [{ id: 'phone', owner_id: 'owner', status: 'active' }, { id: 'other', owner_id: 'another-user' }];
  } };
  const snapshot = await loadDashboard(api, 'owner');
  assert.equal(snapshot.sessions.length, 1);
  assert.equal(chooseSession(snapshot.sessions, '', true), 'phone');
  assert.equal(snapshot.sessions[0].live.streaming, true);
  assert.equal(snapshot.metrics, null);
  assert.match(snapshot.warning, /statistics/);
});

test('sessions remain visible when summaries fail, but a failed session list is reported', async () => {
  const api = { request: async path => {
    if (path === '/dashboard/statistics?own_only=true') return { retained_frames: 0 };
    if (path.startsWith('/dashboard')) throw new TypeError('Load failed');
    return [{ id: 'phone', owner_id: 'owner' }];
  } };
  const snapshot = await loadDashboard(api, 'owner');
  assert.equal(snapshot.sessions[0].id, 'phone');
  assert.equal(snapshot.metrics.retained_frames, 0);
  assert.match(snapshot.warning, /summaries/);
  await assert.rejects(loadDashboard({ request: async () => { throw new Error('Offline'); } }, 'owner'), /Offline/);
});

test('parallel expired requests rotate only once and retry with the new token', async () => {
  let rotations = 0;
  let persisted;
  const api = new ApiClient('https://backend.test', value => { persisted = value; });
  api.setTokens(pair('old'));
  globalThis.fetch = async (url, init) => {
    if (url.endsWith('/auth/refresh')) { rotations++; await new Promise(resolve => setTimeout(resolve, 10)); return json(pair('new')); }
    assert.equal(url, 'https://backend.test/api/v1/sessions?own_only=true');
    return init.headers.Authorization === 'Bearer old' ? json({ detail: 'Expired' }, 401) : json([{ id: 'mobile-session' }]);
  };
  const results = await Promise.all([api.request('/sessions?own_only=true'), api.request('/sessions?own_only=true')]);
  assert.equal(rotations, 1); assert.equal(results[0][0].id, 'mobile-session'); assert.equal(persisted.refresh_token, 'refresh-new');
});

test('revoked refresh clears credentials, while offline refresh preserves them', async () => {
  const api = new ApiClient('https://backend.test');
  api.setTokens({ ...pair(), expires_in: 0 });
  globalThis.fetch = async () => { throw new TypeError('Offline'); };
  await assert.rejects(api.token(), /Offline/); assert.ok(api.tokens);
  globalThis.fetch = async () => json({ detail: 'Revoked' }, 401);
  await assert.rejects(api.token(), e => e instanceof ApiError && e.status === 401); assert.equal(api.tokens, null);
});

test('sign-out during rotation does not restore the previous account', async () => {
  const api = new ApiClient('https://backend.test'); api.setTokens(pair());
  let resolve;
  globalThis.fetch = () => new Promise(done => { resolve = done; });
  const refreshing = api.refresh(); api.setTokens(null); resolve(json(pair('new')));
  await assert.rejects(refreshing, /Sign-in changed/); assert.equal(api.tokens, null);
});

test('multipart voice upload keeps its boundary and uses bearer authorization', async () => {
  const api = new ApiClient('https://backend.test'); api.setTokens(pair());
  const form = new FormData(); form.append('audio', new Blob(['voice']), 'question.webm');
  globalThis.fetch = async (url, init) => {
    assert.equal(url, 'https://backend.test/api/v1/sessions/mobile/questions/audio');
    assert.equal(init.body, form); assert.equal(init.headers['Content-Type'], undefined); assert.equal(init.headers.Authorization, 'Bearer access');
    return json({ question: 'What is here?' });
  };
  assert.equal((await api.upload('/sessions/mobile/questions/audio', form)).question, 'What is here?');
});

test('live HTTP keeps the caller abort signal active after response headers', async () => {
  const api = new ApiClient('https://backend.test'); api.setTokens(pair());
  const controller = new AbortController(); let usedSignal;
  globalThis.fetch = async (url, init) => { assert.ok(!url.includes('access')); usedSignal = init.signal; return new Response('stream'); };
  await api.response('/sessions/mobile/stream/live.mjpeg', { signal: controller.signal }, 0);
  controller.abort(); assert.equal(usedSignal.aborted, true);
});

test('server dependency errors and validation messages remain visible', async () => {
  const api = new ApiClient('https://backend.test');
  globalThis.fetch = async () => json({ error: { message: 'Whisper unavailable' } }, 503);
  await assert.rejects(api.publicRequest('/speech/transcriptions', {}), /Whisper unavailable/);
  globalThis.fetch = async () => json({ detail: [{ msg: 'Invalid email address' }] }, 422);
  await assert.rejects(api.publicRequest('/auth/login', {}), /Invalid email address/);
});

function multipart(jpegs) {
  return Buffer.concat(jpegs.map(jpeg => Buffer.concat([Buffer.from(`--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${jpeg.length}\r\n\r\n`), jpeg, Buffer.from('\r\n')])));
}
test('MJPEG parser handles every possible split position, JPEG marker-like bytes, and multiple parts', () => {
  const images = [Buffer.from([255, 216, 13, 10, 13, 10, 255, 217]), Buffer.from([255, 216, 42, 255, 217])];
  const bytes = multipart(images);
  for (let split = 0; split <= bytes.length; split++) {
    const parser = new MjpegParser();
    const frames = [...parser.push(bytes.subarray(0, split)), ...parser.push(bytes.subarray(split))];
    assert.deepEqual(frames.map(image => [...image]), images.map(image => [...image]));
  }
  const parser = new MjpegParser(); const frames = [];
  for (const value of bytes) frames.push(...parser.push(Uint8Array.of(value)));
  assert.equal(frames.length, 2);
});

test('MJPEG parser rejects malformed and oversized parts without unbounded buffering', () => {
  assert.throws(() => new MjpegParser().push(Buffer.from('--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 999999999\r\n\r\n')), /size limit/);
  assert.throws(() => new MjpegParser().push(Buffer.alloc(8193)), /headers/);
  assert.throws(() => new MjpegParser().push(Buffer.from('--frame\r\nContent-Type: text/html\r\nContent-Length: 3\r\n\r\nabc')), /format/);
});

test('session discovery follows a newly live mobile producer while respecting manual history selection', () => {
  const rows = [{ id: 'history', status: 'closed', live: { streaming: false } }, { id: 'phone', status: 'active', live: { streaming: true } }];
  assert.equal(chooseSession(rows, '', true), 'phone');
  assert.equal(chooseSession(rows, 'history', true), 'phone');
  assert.equal(chooseSession(rows, 'history', false), 'history');
  assert.equal(chooseSession([], 'deleted', false), '');
});

test('event socket authenticates with its first message and never sends tokens in the URL', async () => {
  const sockets = [];
  class Socket {
    sent = [];
    constructor(url) { this.url = url; sockets.push(this); }
    send(value) { this.sent.push(value); }
    close() { this.onclose?.(); }
  }
  globalThis.WebSocket = Socket;
  const api = new ApiClient('https://backend.test'); api.setTokens(pair());
  const events = [];
  const close = subscribeEvents(api, 'mobile', event => events.push(event), () => {});
  try {
    await Promise.resolve();
    const socket = sockets[0]; assert.equal(socket.url, 'wss://backend.test/api/v1/sessions/mobile/events');
    socket.onopen(); assert.deepEqual(JSON.parse(socket.sent[0]), { access_token: 'access' });
    socket.onmessage({ data: JSON.stringify({ type: 'question_answered', question: { id: 'q1' } }) });
    assert.equal(events[0].question.id, 'q1');
  } finally { close(); }
});

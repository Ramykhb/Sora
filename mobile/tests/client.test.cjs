const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { ApiClient, ApiError } = require('../src/lib/api.ts');
const { connectLive, jpegBytes } = require('../src/lib/live.ts');
const { publishVideo } = require('../src/lib/webrtc.ts');
const originalFetch = global.fetch;
const originalSocket = global.WebSocket;
afterEach(() => { global.fetch = originalFetch; global.WebSocket = originalSocket; });
const pair = (access = 'access') => ({ access_token: access, refresh_token: `refresh-${access}`, expires_in: 300, user: { id: 'owner' } });
const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

test('WebRTC publisher sends its gathered video SDP and cleans up a cancelled negotiation', async () => {
  const requests = [];
  const peer = {
    iceGatheringState: 'complete', localDescription: null,
    async createOffer() { return { type: 'offer', sdp: 'video offer' }; },
    async setLocalDescription(offer) { this.localDescription = { ...offer, sdp: offer.sdp + '\na=candidate:gathered' }; },
    async setRemoteDescription(answer) { this.answer = answer; },
    addEventListener() {}, removeEventListener() {},
  };
  const api = { async request(path, method, body) {
    requests.push({ path, method, body });
    return { type: 'answer', sdp: 'video answer', connection_id: 'producer-id' };
  } };
  assert.equal(await publishVideo(api, 'session', peer, new AbortController().signal), 'producer-id');
  assert.equal(requests[0].path, '/sessions/session/stream/offer');
  assert.match(requests[0].body.sdp, /candidate:gathered/);
  assert.deepEqual(peer.answer, { type: 'answer', sdp: 'video answer' });
  const controller = new AbortController();
  api.request = async (path, method) => {
    requests.push({ path, method });
    if (method === 'POST') controller.abort();
    return { type: 'answer', sdp: 'late answer', connection_id: 'cancelled-id' };
  };
  await assert.rejects(publishVideo(api, 'session', peer, controller.signal), /cancelled/);
  assert.equal(requests.at(-1).path, '/sessions/session/stream/connections/cancelled-id');
  assert.equal(requests.at(-1).method, 'DELETE');
});

test('parallel 401 responses share one refresh and retry with the rotated token', async () => {
  let rotations = 0;
  const saved = [];
  const api = new ApiClient('https://example.test', async value => { saved.push(value); });
  await api.setTokens(pair('old'));
  global.fetch = async (url, init) => {
    if (url.endsWith('/auth/refresh')) { rotations++; await new Promise(resolve => setTimeout(resolve, 15)); return json(pair('new')); }
    assert.equal(url, 'https://example.test/api/v1/sessions');
    return init.headers.Authorization === 'Bearer old' ? json({ detail: 'Expired' }, 401) : json(['owned']);
  };
  assert.deepEqual(await Promise.all([api.request('/sessions'), api.request('/sessions')]), [['owned'], ['owned']]);
  assert.equal(rotations, 1);
  assert.equal(saved.at(-1).refresh_token, 'refresh-new');
});

test('revoked refresh clears credentials and never retries a protected action', async () => {
  let persisted = pair();
  const api = new ApiClient('https://example.test', async value => { persisted = value; });
  await api.setTokens({ ...pair(), expires_in: 0 });
  global.fetch = async url => { assert.ok(url.endsWith('/auth/refresh')); return json({ detail: 'Revoked' }, 401); };
  await assert.rejects(api.request('/sessions'), e => e instanceof ApiError && e.status === 401);
  assert.equal(persisted, null); assert.equal(api.tokens, null);
});

test('transient refresh failure preserves credentials for a retry', async () => {
  const api = new ApiClient('https://example.test', async () => {});
  await api.setTokens({ ...pair(), expires_in: 0 });
  global.fetch = async () => { throw new TypeError('Offline'); };
  await assert.rejects(api.token(), /Offline/);
  assert.equal(api.tokens.refresh_token, 'refresh-access');
  global.fetch = async () => json(pair('recovered'));
  assert.equal(await api.token(), 'recovered');
});

test('multipart uploads keep their boundary and retry after refresh', async () => {
  const api = new ApiClient('https://example.test', async () => {});
  await api.setTokens(pair());
  const form = new FormData(); form.append('audio', new Blob(['voice']), 'question.webm');
  global.fetch = async (_url, init) => {
    assert.equal(init.body, form); assert.equal(init.headers['Content-Type'], undefined);
    assert.equal(init.headers.Authorization, 'Bearer access');
    return json({ question: 'What is here?' });
  };
  assert.equal((await api.upload('/sessions/id/questions/audio', form)).question, 'What is here?');
});

test('validation errors and dependency errors remain actionable', async () => {
  const api = new ApiClient('https://example.test', async () => {});
  global.fetch = async () => json({ detail: [{ msg: 'Password too short' }] }, 422);
  await assert.rejects(api.publicRequest('/auth/register', {}), /Password too short/);
  global.fetch = async () => json({ error: { code: 'speech_unavailable', message: 'Install Whisper' } }, 503);
  await assert.rejects(api.publicRequest('/speech/transcriptions', {}), /Install Whisper/);
});

test('logout during rotation cannot restore the old sign-in', async () => {
  const api = new ApiClient('https://example.test', async () => {});
  await api.setTokens(pair());
  let resolve;
  global.fetch = () => new Promise(done => { resolve = done; });
  const rotating = api.refresh();
  await api.setTokens(null);
  resolve(json(pair('rotated')));
  await assert.rejects(rotating, /Sign-in changed/); assert.equal(api.tokens, null);
});

test('live transport authenticates before accepting binary frames and respects backpressure', async () => {
  const sockets = [];
  class Socket {
    static OPEN = 1;
    readyState = 1; bufferedAmount = 0; sent = [];
    constructor(url) { this.url = url; sockets.push(this); }
    send(value) { this.sent.push(value); }
    close() { this.onclose?.(); }
  }
  global.WebSocket = Socket;
  const api = new ApiClient('https://example.test', async () => {});
  await api.setTokens(pair());
  const live = connectLive(api, '/sessions/id/stream/frames', () => {}, () => {});
  try {
    await Promise.resolve();
    const ws = sockets[0];
    assert.equal(ws.url, 'wss://example.test/api/v1/sessions/id/stream/frames');
    assert.ok(!ws.url.includes('access'));
    ws.onopen(); assert.deepEqual(JSON.parse(ws.sent[0]), { access_token: 'access' });
    const jpeg = jpegBytes('/9j/2Q==');
    assert.deepEqual([...new Uint8Array(jpeg)], [255, 216, 255, 217]);
    assert.equal(live.send(jpeg), false);
    ws.onmessage({ data: JSON.stringify({ type: 'ready' }) });
    assert.equal(live.send(jpeg), true); assert.equal(ws.sent[1], jpeg);
    ws.bufferedAmount = 600000; assert.equal(live.send(jpeg), false);
    live.close(); assert.equal(live.send(jpeg), false);
  } finally { live.close(); }
});

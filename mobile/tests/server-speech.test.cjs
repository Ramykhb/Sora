const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/server-speech.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const audio = JSON.stringify({ type: 'audio', data: 'UklGRg==' }) + '\n';
const done = '{"type":"done"}\n';
const encode = text => new TextEncoder().encode(text);

function setup({ response, write, platform = 'ios', autoStart = true } = {}) {
  const requests = [], players = [], files = [];
  const exports = {};
  let network;
  const api = { async response(path, options, fetcher) {
    requests.push({ path, options, fetcher });
    return response ? response() : { body: new ReadableStream({ start(controller) { network = controller; } }) };
  } };
  vm.runInNewContext(source, {
    exports, Date, Error, setTimeout, clearTimeout, AbortController, TextDecoder,
    require(name) {
      if (name === 'react-native') return { Platform: { OS: platform } };
      if (name === 'expo/fetch') return { fetch: async () => { throw new Error('Mock API should handle the transport'); } };
      if (name === 'expo-file-system') return { Paths: { cache: 'cache' }, File: class {
        constructor(_, name) { this.uri = name; this.exists = false; this.deleted = false; files.push(this); }
        async write(data, options) { this.data = data; this.encoding = options.encoding; this.exists = true; await write?.(); }
        delete() { this.deleted = true; this.exists = false; }
      } };
      if (name === 'expo-audio') return { createAudioPlaylist() {
        const player = { sources: [], plays: 0, destroyed: false, unsubscribed: false,
          addListener(_, callback) { this.emit = callback; return { remove: () => { this.unsubscribed = true; } }; },
          add(source) { this.sources.push(source); },
          play() { this.plays++; if (autoStart) this.emit({ playing: true }); },
          pause() {}, destroy() { this.destroyed = true; },
        };
        players.push(player); return player;
      } };
      throw new Error(name);
    },
  });
  return { speech: exports.serverSpeech, api, requests, players, files,
    send(text) { network.enqueue(encode(text)); }, close() { network.close(); }, error() { network.error(new Error('Network lost')); },
  };
}
async function flush() { for (let i = 0; i < 24; i++) await Promise.resolve(); }

async function start(app, callbacks = {}, prepare) {
  app.speech.configure(app.api);
  const pending = app.speech.speak('اِبْدَأْ البث', callbacks, prepare);
  await flush(); app.send(audio); await flush();
  return pending;
}

test('first audio starts before the rest is generated, through authenticated streaming fetch', async () => {
  const app = setup();
  let completed = 0;
  assert.equal(await start(app, { onDone() { completed++; } }), true);
  assert.equal(app.requests[0].path, '/speech/stream');
  assert.equal(typeof app.requests[0].fetcher, 'function');
  assert.deepEqual(JSON.parse(app.requests[0].options.body), { text: 'اِبْدَأْ البث', language: 'ar', provider: 'gemini' });
  assert.equal(app.players[0].sources.length, 1);
  assert.equal(app.files[0].encoding, 'base64');
  assert.equal(completed, 0);
  app.send(audio + done); app.close(); await flush();
  assert.equal(app.players[0].sources.length, 2);
  app.players[0].emit({ didJustFinish: true });
  assert.equal(completed, 1);
  assert.equal(app.players[0].destroyed, true);
  assert.ok(app.files.every(file => file.deleted));
});

test('stop aborts a request before the first frame and settles without fallback', async () => {
  const app = setup();
  app.speech.configure(app.api);
  const pending = app.speech.speak('مرحبا', {});
  await flush(); app.speech.stop();
  assert.equal(await pending, true);
  assert.equal(app.requests[0].options.signal.aborted, true);
  assert.equal(app.players[0].destroyed, true);
});

test('stop during an asynchronous frame write removes late temporary files', async () => {
  let resolve;
  const app = setup({ write: () => new Promise(done => { resolve = done; }) });
  app.speech.configure(app.api);
  const pending = app.speech.speak('مرحبا', {});
  await flush(); app.send(audio); await flush();
  app.speech.stop(); resolve(); await flush();
  assert.equal(await pending, true);
  assert.equal(app.files[0].deleted, true);
  assert.equal(app.players[0].sources.length, 0);
});

test('first chunk waits for the audio route while the network request is already active', async () => {
  let ready;
  const app = setup();
  app.speech.configure(app.api);
  const pending = app.speech.speak('مرحبا', {}, () => new Promise(resolve => { ready = resolve; }));
  await flush(); app.send(audio); await flush();
  assert.equal(app.players[0].sources.length, 1);
  assert.equal(app.players[0].plays, 0);
  ready(); assert.equal(await pending, true);
  app.speech.stop();
});

test('a drained queue resumes when the next audio segment arrives', async () => {
  const app = setup();
  await start(app);
  app.players[0].emit({ didJustFinish: true });
  assert.equal(app.players[0].destroyed, false);
  app.send(audio + done); app.close(); await flush();
  assert.equal(app.players[0].plays, 2);
  app.players[0].emit({ didJustFinish: true });
  assert.equal(app.players[0].destroyed, true);
});

test('missing credentials and provider errors request local fallback', async () => {
  const app = setup({ response: async () => { throw new Error('HTTP 429'); } });
  assert.equal(await app.speech.speak('مرحبا', {}), false);
  app.speech.configure(app.api);
  assert.equal(await app.speech.speak('مرحبا', {}), false);
  assert.equal(app.players[0].destroyed, true);
});

test('network failure after starting releases resources and reports the error once', async () => {
  const app = setup();
  let errors = 0;
  await start(app, { onError() { errors++; } });
  app.error(); await flush();
  assert.equal(errors, 1);
  assert.equal(app.players[0].destroyed, true);
  assert.ok(app.files.every(file => file.deleted));
});

test('partial network lines are assembled before adding a frame', async () => {
  const app = setup();
  app.speech.configure(app.api);
  const pending = app.speech.speak('مرحبا', {});
  await flush(); app.send(audio.slice(0, 10)); await flush();
  assert.equal(app.players[0].sources.length, 0);
  app.send(audio.slice(10)); assert.equal(await pending, true);
  app.speech.stop();
});

test('web streams playable data URLs without native temporary files', async () => {
  const app = setup({ platform: 'web' });
  await start(app);
  assert.equal(app.players[0].sources[0].uri, 'data:audio/wav;base64,UklGRg==');
  assert.equal(app.files.length, 0);
  app.speech.stop();
});

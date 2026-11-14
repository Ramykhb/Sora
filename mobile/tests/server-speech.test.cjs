const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/server-speech.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function setup({ response, write, createError } = {}) {
  const requests = [], files = [], players = [];
  const exports = {};
  const api = { async response(path, options) {
    requests.push({ path, options });
    return response ? response() : { arrayBuffer: async () => new ArrayBuffer(8) };
  } };
  vm.runInNewContext(source, { exports, Date, Uint8Array, Error, require(name) {
    if (name === 'react-native') return { Platform: { OS: 'ios' } };
    if (name === 'expo-file-system') return { Paths: { cache: 'cache' }, File: class {
      constructor(_, name) { this.uri = name; this.exists = false; this.deleted = false; files.push(this); }
      async write() { this.exists = true; await write?.(); }
      delete() { this.deleted = true; this.exists = false; }
    } };
    if (name === 'expo-audio') return { createAudioPlayer(source) {
      if (createError) throw new Error('Player unavailable');
      const player = { source, played: false, removed: false, unsubscribed: false,
        addListener(_, callback) { this.emit = callback; return { remove: () => { this.unsubscribed = true; } }; },
        play() { this.played = true; }, pause() {}, remove() { this.removed = true; },
      };
      players.push(player); return player;
    } };
    throw new Error(name);
  } });
  const speech = exports.serverSpeech;
  return { speech, api, requests, files, players };
}

test('Arabic synthesis uses the authenticated API and cleans up the player and WAV on completion', async () => {
  const app = setup();
  app.speech.configure(app.api);
  let done = 0;
  assert.equal(await app.speech.speak('اِبْدَأْ البث', { onDone() { done++; } }), true);
  assert.equal(app.requests[0].path, '/speech/synthesis');
  assert.deepEqual(JSON.parse(app.requests[0].options.body), { text: 'اِبْدَأْ البث', language: 'ar', provider: 'gemini' });
  assert.equal(app.players[0].played, true);
  assert.equal(app.players[0].volume, 1);
  app.players[0].emit({ didJustFinish: true });
  assert.equal(done, 1);
  assert.equal(app.files[0].deleted, true);
  assert.equal(app.players[0].removed, true);
  assert.equal(app.players[0].unsubscribed, true);
});

test('stopping a pending cloud request prevents stale playback and native fallback', async () => {
  let resolve;
  const app = setup({ response: () => new Promise(done => { resolve = done; }) });
  app.speech.configure(app.api);
  const pending = app.speech.speak('مرحبا', {});
  app.speech.stop();
  resolve({ arrayBuffer: async () => new ArrayBuffer(8) });
  assert.equal(await pending, true);
  assert.equal(app.players.length, 0);
  assert.equal(app.files.length, 0);
});

test('stopping during an asynchronous file write removes the file without playing it', async () => {
  let resolve;
  const app = setup({ write: () => new Promise(done => { resolve = done; }) });
  app.speech.configure(app.api);
  const pending = app.speech.speak('مرحبا', {});
  for (let i = 0; i < 8; i++) await Promise.resolve();
  app.speech.stop(); resolve();
  assert.equal(await pending, true);
  assert.equal(app.files[0].deleted, true);
  assert.equal(app.players.length, 0);
});

test('missing credentials and provider errors request device fallback', async () => {
  const app = setup({ response: async () => { throw new Error('Unavailable'); } });
  assert.equal(await app.speech.speak('مرحبا', {}), false);
  assert.equal(app.requests.length, 0);
  app.speech.configure(app.api);
  assert.equal(await app.speech.speak('مرحبا', {}), false);
  assert.equal(app.players.length, 0);
});

test('player construction failures remove temporary media before device fallback', async () => {
  const app = setup({ createError: true });
  app.speech.configure(app.api);
  assert.equal(await app.speech.speak('مرحبا', {}), false);
  assert.equal(app.files[0].deleted, true);
});

test('playback errors release resources and notify the speech gate', async () => {
  const app = setup();
  app.speech.configure(app.api);
  let errors = 0;
  await app.speech.speak('مرحبا', { onError() { errors++; } });
  app.players[0].emit({ error: 'Unable to decode' });
  assert.equal(errors, 1);
  assert.equal(app.files[0].deleted, true);
});

test('signing out invalidates pending cloud speech', async () => {
  let resolve;
  const app = setup({ response: () => new Promise(done => { resolve = done; }) });
  const disconnect = app.speech.configure(app.api);
  const pending = app.speech.speak('مرحبا', {});
  disconnect();
  resolve({ arrayBuffer: async () => new ArrayBuffer(8) });
  assert.equal(await pending, true);
  assert.equal(app.players.length, 0);
  assert.equal(await app.speech.speak('مرحبا', {}), false);
});

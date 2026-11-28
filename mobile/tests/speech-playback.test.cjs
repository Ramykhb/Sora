const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { SpeechController } = require('../src/lib/speech-policy.ts');
const { VoiceAudioGate } = require('../src/lib/voice-commands.ts');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/speech.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
function setup(configure = async () => {}, cloud = {}, voices = [
  { identifier: 'ar-sa-compact', language: 'ar-SA', quality: 'Default' },
  { identifier: 'ar-eg-enhanced', language: 'ar-EG', quality: 'Enhanced' },
]) {
  const spoken = [], modes = [], recordings = [];
  const gate = new VoiceAudioGate();
  const exports = {};
  vm.runInNewContext(source, { exports, require(name) {
    if (name === 'expo-audio') return { async setAudioModeAsync(mode) { modes.push(mode); await configure(); } };
    if (name === 'expo-speech') return {
      async stop() {}, speak(text, options) { spoken.push({ text, options }); },
      VoiceQuality: { Default: 'Default', Enhanced: 'Enhanced' },
      async getAvailableVoicesAsync() { return typeof voices === 'function' ? voices() : voices; },
    };
    if (name === './speech-policy') return { SpeechController };
    if (name === './voice-commands') return { voiceAudioGate: gate };
    if (name === './voice-language') return require('../src/lib/voice-language.ts');
    if (name === './arabic-recordings') return { arabicAlertRecording: text => /باباً مغلقاً/.test(text) ? 'closedDoor' : 'obstacle', arabicRecordings: { stop() {}, speak(key, callbacks) { recordings.push({ key, callbacks }); } } };
    if (name === './server-speech') return { serverSpeech: { stop() {}, async speak() { return false; }, ...cloud } };
    throw new Error(name);
  } });
  return { speech: exports.speech, spoken, modes, gate, recordings };
}

test('automatic answers use the configured playback session and resume listening after speech', async () => {
  const { speech, spoken, modes, gate } = setup();
  await speech.answer('A chair is ahead.', 'en');
  assert.equal(modes[0].playsInSilentMode, true);
  assert.equal(modes[0].allowsRecording, false);
  assert.equal(spoken[0].options.useApplicationAudioSession, true);
  assert.equal(gate.paused, false);
  assert.equal(gate.playing, true);
  spoken[0].options.onDone();
  assert.equal(gate.paused, false);
  assert.equal(gate.playing, false);
});

test('unavailable Arabic cloud speech reads the answer using an installed Arabic voice', async () => {
  const { speech, spoken, recordings } = setup();
  await speech.answer('مرحباً، الطريق أمامك.', 'ar-SA');
  assert.equal(spoken.length, 1);
  assert.equal(spoken[0].text, 'مرحباً، الطريق أمامك.');
  assert.equal(spoken[0].options.voice, 'ar-sa-compact');
  assert.equal(recordings.length, 0);
});

test('cloud exceptions also fall back locally and completion releases the audio gate', async () => {
  const app = setup(undefined, { async speak() { throw new Error('Offline'); } });
  await app.speech.answer('هذه إجابة محفوظة.', 'ar');
  assert.equal(app.spoken[0].text, 'هذه إجابة محفوظة.');
  assert.equal(app.spoken[0].options.voice, 'ar-eg-enhanced');
  app.spoken[0].options.onDone();
  assert.equal(app.gate.playing, false);
});

test('missing Arabic voices keep the unavailable clip instead of using another language', async () => {
  const app = setup(undefined, {}, [{ identifier: 'en', language: 'en-US' }]);
  await app.speech.answer('مرحبا', 'ar');
  assert.equal(app.spoken.length, 0);
  assert.equal(app.recordings[0].key, 'unavailable');
});

test('stopping during voice lookup cancels local fallback', async () => {
  let resolve;
  const app = setup(undefined, {}, () => new Promise(done => { resolve = done; }));
  const pending = app.speech.answer('مرحبا', 'ar');
  for (let i = 0; i < 30 && !resolve; i++) await Promise.resolve();
  await app.speech.stop();
  resolve([{ identifier: 'ar', language: 'ar-SA' }]);
  await pending;
  assert.equal(app.spoken.length, 0);
  assert.equal(app.recordings.length, 0);
});

test('Arabic start prompts supply pronunciation vowels without changing other words', async () => {
  const cloud = [];
  const { speech, spoken } = setup(undefined, { async speak(text) { cloud.push(text); return true; } });
  const prompt = 'ابدأ البث. قل «يا سورا، ابدأ الاستماع». لا تتوقف أبداً.';
  await speech.answer(prompt, 'ar-SA');
  assert.equal(cloud[0], 'اِبْدَأْ البث. قل «يا سورا، اِبْدَأْ الاستماع». لا تتوقف أبداً.');
  await speech.answer('اِبْدَأْ البث، ابدأنا، أبدان، أبدا، أبداً، ابدا.', 'ar');
  assert.equal(cloud[1], 'اِبْدَأْ البث، ابدأنا، أبدان، أبدا، أبداً، ابدا.');
  await speech.answer('ابدأ', 'en-US');
  assert.equal(cloud[2], 'ابدأ');
  assert.equal(spoken.length, 0);
});

test('stopping while audio config is pending prevents a delayed answer from speaking', async () => {
  let ready;
  const app = setup(() => new Promise(resolve => { ready = resolve; }));
  const pending = app.speech.answer('Old answer.', 'en');
  for (let i = 0; i < 30 && !ready; i++) await Promise.resolve();
  assert.equal(app.gate.paused, false);
  assert.equal(app.gate.playing, true);
  await app.speech.stop();
  ready(); await pending;
  assert.equal(app.spoken.length, 0);
  assert.equal(app.gate.paused, false);
  assert.equal(app.gate.playing, false);
});

test('Arabic answers use server speech and release the playback gate on completion', async () => {
  let callbacks;
  const cloud = [];
  const app = setup(undefined, { async speak(text, options) { cloud.push(text); callbacks = options; return true; } });
  await app.speech.answer('ابدأ البث', 'ar-SA');
  assert.deepEqual(cloud, ['اِبْدَأْ البث']);
  assert.equal(app.spoken.length, 0);
  assert.equal(app.gate.playing, true);
  callbacks.onDone();
  assert.equal(app.gate.playing, false);
});

test('stopping during a cloud request prevents both remote and fallback playback', async () => {
  let resolve;
  let stops = 0;
  const app = setup(undefined, { stop() { stops++; }, speak() { return new Promise(done => { resolve = done; }); } });
  const pending = app.speech.answer('مرحبا', 'ar');
  for (let i = 0; i < 15; i++) await Promise.resolve();
  await app.speech.stop();
  resolve(false);
  await pending;
  assert.equal(app.spoken.length, 0);
  assert.equal(app.gate.playing, false);
  assert.ok(stops >= 2);
});

test('Arabic stream warnings keep the female voice without making cloud requests', async () => {
  const app = setup(undefined, { async speak() { throw new Error('Alerts must not wait on cloud synthesis'); } });
  await app.speech.alert('urgent', 'يوجد جسم في وسط صورة الكاميرا. لا يمكنني تقييم المسار كاملاً.', 'ar', new Date(Date.now() + 5000).toISOString());
  assert.equal(app.spoken.length, 0);
  assert.equal(app.recordings[0].key, 'obstacle');
  app.recordings[0].callbacks.onDone();
  assert.equal(app.gate.playing, false);
  await app.speech.alert('door', 'يبدو أن هناك باباً مغلقاً في وسط صورة الكاميرا.', 'ar', new Date(Date.now() + 5000).toISOString());
  assert.equal(app.recordings[1].key, 'closedDoor');
  assert.equal(app.spoken.length, 0);
});

test('audio setup errors release the microphone gate', async () => {
  const app = setup(async () => { throw new Error('Audio unavailable'); });
  await assert.rejects(app.speech.answer('An answer.', 'en'), /Audio unavailable/);
  assert.equal(app.spoken.length, 0);
  assert.equal(app.gate.paused, false);
  assert.equal(app.gate.playing, false);
});


test('an answer waits for the recognition route to settle and reuses it without lowering startup volume', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 10000 });
  const app = setup();
  app.gate.setRecognitionState('starting');
  const pending = app.speech.answer('I detect a laptop.', 'en');
  for (let i = 0; i < 8; i++) await Promise.resolve();
  assert.equal(app.spoken.length, 0);
  app.gate.setRecognitionState('ready');
  t.mock.timers.tick(149);
  for (let i = 0; i < 8; i++) await Promise.resolve();
  assert.equal(app.spoken.length, 0);
  t.mock.timers.tick(1);
  await pending;
  assert.equal(app.modes.length, 0, 'do not reconfigure an active recognition audio session');
  assert.equal(app.spoken[0].text, 'I detect a laptop.');
  assert.equal(app.spoken[0].options.volume, 1);
  assert.equal(app.spoken[0].options.useApplicationAudioSession, true);
});

test('stopping an answer while recognition is restarting prevents delayed playback', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 10000 });
  const app = setup();
  app.gate.setRecognitionState('starting');
  const pending = app.speech.answer('An old answer.', 'en');
  for (let i = 0; i < 8; i++) await Promise.resolve();
  await app.speech.stop();
  app.gate.setRecognitionState('ready');
  t.mock.timers.tick(150);
  await pending;
  assert.equal(app.spoken.length, 0);
  assert.equal(app.gate.playing, false);
});

test('an unavailable recognizer cannot leave answer playback waiting indefinitely', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 10000 });
  const app = setup();
  app.gate.setRecognitionState('starting');
  const pending = app.speech.answer('A laptop.', 'en');
  for (let i = 0; i < 8; i++) await Promise.resolve();
  t.mock.timers.tick(2000);
  await pending;
  assert.equal(app.spoken.length, 1);
  assert.equal(app.modes[0].allowsRecording, true);
});

test('Arabic remembered-target alerts speak the target instead of a generic obstacle recording', async () => {
  const cloud = [];
  let callbacks;
  const app = setup(undefined, { async speak(text, options) { cloud.push(text); callbacks = options; return true; } });
  const text = 'تم اكتشاف: علامة توقف.';
  await app.speech.alert('remembered-stop', text, 'ar', new Date(Date.now() + 5000).toISOString(), true);
  assert.deepEqual(cloud, [text]);
  assert.equal(app.recordings.length, 0);
  callbacks.onDone();
  assert.equal(app.gate.playing, false);
});

test('English and French answers use the server voice in their base language', async () => {
  const cloud = [];
  let callbacks;
  const app = setup(undefined, { async speak(text, options, _, language) { cloud.push([text, language]); callbacks = options; return true; } });
  await app.speech.answer('A chair is ahead.', 'en-US');
  await app.speech.answer('Une chaise est devant vous.', 'fr-FR');
  assert.deepEqual(cloud, [['A chair is ahead.', 'en'], ['Une chaise est devant vous.', 'fr']]);
  assert.equal(app.spoken.length, 0);
  callbacks.onDone();
  assert.equal(app.gate.playing, false);
});

test('unreachable server speech reads English and French with the phone voice', async () => {
  const app = setup(undefined, { async speak() { throw new Error('Offline'); } });
  await app.speech.answer('Une chaise.', 'fr-FR');
  assert.equal(app.spoken[0].text, 'Une chaise.');
  assert.equal(app.spoken[0].options.language, 'fr-FR');
  assert.equal(app.spoken[0].options.voice, undefined);
});

test('English and French warnings never wait for the server', async () => {
  const app = setup(undefined, { async speak() { throw new Error('Alerts must not wait on the server'); } });
  const expires = new Date(Date.now() + 5000).toISOString();
  await app.speech.alert('en-warning', 'Obstacle ahead.', 'en', expires);
  await app.speech.alert('fr-target', 'Détecté : panneau stop.', 'fr', expires, true);
  assert.deepEqual(app.spoken.map(item => item.text), ['Obstacle ahead.', 'Détecté : panneau stop.']);
});

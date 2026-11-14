const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { SpeechController } = require('../src/lib/speech-policy.ts');

function setup() {
  const spoken = [];
  const driver = { async stop() {}, speak(text, options) { spoken.push({ text, options }); } };
  return { speech: new SpeechController(driver), spoken, driver };
}

test('a fresh obstacle alert interrupts playback and cannot be replaced by an automatic answer', async () => {
  const { speech, spoken } = setup();
  let interruptions = 0;
  speech.registerInterruptor(() => interruptions++);
  await speech.answer('An earlier answer', 'en');
  await speech.alert('alert-1', 'Object in the camera center', 'en', new Date(Date.now() + 2000).toISOString());
  await speech.answer('A delayed answer', 'en');
  assert.deepEqual(spoken.map(item => item.text), ['An earlier answer', 'Object in the camera center']);
  assert.equal(interruptions, 2);
  spoken[1].options.onDone();
  await speech.answer('Next answer', 'en');
  assert.equal(spoken.at(-1).text, 'Next answer');
});

test('expired, invalid and duplicate alerts never enter the speech queue', async () => {
  const { speech, spoken } = setup();
  await speech.alert('old', 'Old', 'en', new Date(Date.now() - 1).toISOString());
  await speech.alert('invalid', 'Invalid', 'en', 'invalid');
  const deadline = new Date(Date.now() + 2000).toISOString();
  await speech.alert('one', 'Once', 'fr', deadline);
  await speech.alert('one', 'Once', 'fr', deadline);
  assert.deepEqual(spoken.map(item => item.text), ['Once']);
});

test('pausing during speech interruption cancels the pending alert', async () => {
  const { speech, spoken, driver } = setup();
  let release;
  driver.stop = () => new Promise(resolve => { release = resolve; });
  const pending = speech.alert('one', 'Object', 'en', new Date(Date.now() + 2000).toISOString());
  const finishFirst = release;
  const stopping = speech.stop();
  finishFirst(); release();
  await Promise.all([pending, stopping]);
  assert.equal(spoken.length, 0);
});

test('result playback receives completion, stop and error callbacks without changing ordinary answers', async () => {
  const { speech, spoken } = setup();
  let completed = 0;
  await speech.answer('Read this text', 'en', () => completed++);
  spoken[0].options.onDone();
  spoken[0].options.onStopped();
  spoken[0].options.onError(new Error('Audio unavailable'));
  assert.equal(completed, 3);
  await speech.answer('An ordinary answer', 'fr');
  assert.equal(spoken[1].options.language, 'fr');
  assert.equal(spoken[1].options.onDone, undefined);
});


test('global mute stops playback and suppresses answers and alerts until unmuted', async () => {
  const { speech, spoken } = setup();
  let interrupted = 0, completed = 0;
  speech.registerInterruptor(() => interrupted++);
  await speech.answer('Speaking', 'en');
  await speech.setMuted(true);
  assert.equal(speech.isMuted, true);
  assert.equal(interrupted, 2);
  await speech.answer('Silent answer', 'en', () => completed++);
  await speech.alert('muted-alert', 'Silent alert', 'en', new Date(Date.now() + 2000).toISOString());
  assert.equal(spoken.length, 1);
  assert.equal(completed, 1);
  await speech.setMuted(false);
  await speech.answer('Voice unmuted', 'en');
  assert.equal(spoken.at(-1).text, 'Voice unmuted');
});

test('repeat preserves the answer and language across feedback, alerts, and stopping', async () => {
  const { speech, spoken } = setup();
  speech.rememberAnswer('Une chaise est devant la porte.', 'fr');
  await speech.answer('Stream paused.', 'en');
  await speech.alert('new-alert', 'Object in the center.', 'en', new Date(Date.now() + 2000).toISOString());
  await speech.stop();
  assert.equal(await speech.repeatLastAnswer(), true);
  assert.equal(spoken.at(-1).text, 'Une chaise est devant la porte.');
  assert.equal(spoken.at(-1).options.language, 'fr');
});

for (const [language, route] of [
  ['en', 'Cafe is approximately 500 m away on foot. Walking directions from Google Maps:\n1. Head north (100 m).'],
  ['fr', 'Cafe est à environ 500 m à pied. Itinéraire piéton de Google Maps :\n1. Tournez à droite (100 m).'],
  ['ar', 'يقع Cafe على بُعد نحو 500 m سيراً على الأقدام. اتجاهات المشي من Google Maps:\n1. انعطف يميناً (100 m).'],
]) {
  test(`repeat directions retains the complete ${language} route after another answer`, async () => {
    const { speech, spoken } = setup();
    speech.rememberAnswer(route, language);
    speech.rememberAnswer('A door is visible.', 'en');
    assert.equal(await speech.repeatLastAnswer(), true);
    assert.equal(spoken.at(-1).text, 'A door is visible.');
    assert.equal(await speech.repeatLastAnswer(true), true);
    assert.equal(spoken.at(-1).text, route);
    assert.equal(spoken.at(-1).options.language, language);
  });
}

test('missing and cleared replay history never falls back to unrelated speech', async () => {
  const { speech, spoken } = setup();
  await speech.answer('There is no answer to repeat yet.', 'en');
  assert.equal(await speech.repeatLastAnswer(), false);
  speech.rememberAnswer('A chair.', 'en');
  assert.equal(await speech.repeatLastAnswer(true), false);
  speech.clearHistory();
  assert.equal(await speech.repeatLastAnswer(), false);
  assert.equal(spoken.length, 1);
});

test('mute suppresses replay without deleting the remembered response', async () => {
  const { speech, spoken } = setup();
  speech.rememberAnswer('A chair.', 'en');
  await speech.setMuted(true);
  await speech.repeatLastAnswer();
  assert.equal(spoken.length, 0);
  await speech.setMuted(false);
  await speech.repeatLastAnswer();
  assert.equal(spoken[0].text, 'A chair.');
});

const route = 'Cafe is approximately 500 m away on foot. Walking directions from Google Maps:\n1. Head north (100 m).\n2. Turn right (400 m).\nWalking routes may be missing sidewalks. This overview does not track progress.';

test('a route starts with its summary, first step and warnings, then moves one step at a time', async () => {
  const { speech, spoken } = setup();
  await speech.answer(route, 'en');
  assert.match(spoken[0].text, /Cafe.*500 m/);
  assert.match(spoken[0].text, /1\. Head north/);
  assert.match(spoken[0].text, /missing sidewalks/);
  assert.doesNotMatch(spoken[0].text, /2\. Turn right/);
  speech.rememberAnswer(route, 'en');
  await speech.moveRouteStep(1);
  assert.equal(spoken.at(-1).text, '2. Turn right (400 m).');
  speech.rememberAnswer(route, 'en'); // Duplicate live delivery must preserve progress.
  assert.equal(speech.getRoutePlayback().index, 1);
  await speech.moveRouteStep(1);
  assert.equal(speech.getRoutePlayback().index, 1);
  assert.match(spoken.at(-1).text, /last step/);
  await speech.moveRouteStep(-1);
  assert.equal(spoken.at(-1).text, '1. Head north (100 m).');
  await speech.moveRouteStep(-1);
  assert.equal(speech.getRoutePlayback().index, 0);
  assert.match(spoken.at(-1).text, /first step/);
});

test('full route expands every step and preserves the cursor through unrelated answers and alerts', async () => {
  const { speech, spoken } = setup();
  speech.rememberAnswer(route, 'fr');
  await speech.moveRouteStep(1);
  speech.rememberAnswer('A chair is ahead.', 'en');
  await speech.alert('route-alert', 'Obstacle.', 'en', new Date(Date.now() + 2000).toISOString());
  await speech.stop();
  await speech.showFullRoute();
  assert.equal(spoken.at(-1).text, route);
  assert.equal(spoken.at(-1).options.language, 'fr');
  assert.equal(speech.getRoutePlayback().full, true);
  assert.equal(speech.getRoutePlayback().index, 1);
  await speech.moveRouteStep(-1);
  assert.equal(speech.getRoutePlayback().full, false);
  assert.equal(spoken.at(-1).text, '1. Head north (100 m).');
});

test('new routes reset progress and clearing history removes route controls', async () => {
  const { speech } = setup();
  assert.equal(await speech.moveRouteStep(1), false);
  assert.equal(await speech.showFullRoute(), false);
  let notifications = 0;
  const unsubscribe = speech.subscribeRoute(() => notifications++);
  speech.rememberAnswer(route, 'en');
  await speech.moveRouteStep(1);
  speech.rememberAnswer(route.replace('Cafe', 'Library'), 'en');
  assert.equal(speech.getRoutePlayback().index, 0);
  assert.equal(speech.getRoutePlayback().full, false);
  speech.clearHistory();
  assert.equal(speech.getRoutePlayback(), null);
  assert.equal(await speech.moveRouteStep(-1), false);
  assert.equal(notifications, 4);
  unsubscribe();
});

test('route display and cursor controls still work when voice is muted', async () => {
  const { speech, spoken } = setup();
  speech.rememberAnswer(route, 'en');
  await speech.setMuted(true);
  await speech.moveRouteStep(1);
  await speech.showFullRoute();
  assert.equal(speech.getRoutePlayback().index, 1);
  assert.equal(speech.getRoutePlayback().full, true);
  assert.equal(spoken.length, 0);
});

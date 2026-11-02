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

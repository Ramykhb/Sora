const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { SpeechController } = require('../src/lib/speech-policy.ts');
const { VoiceAudioGate } = require('../src/lib/voice-commands.ts');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/speech.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
function setup(configure = async () => {}) {
  const spoken = [], modes = [];
  const gate = new VoiceAudioGate();
  const exports = {};
  vm.runInNewContext(source, { exports, require(name) {
    if (name === 'expo-audio') return { async setAudioModeAsync(mode) { modes.push(mode); await configure(); } };
    if (name === 'expo-speech') return { async stop() {}, speak(text, options) { spoken.push({ text, options }); } };
    if (name === './speech-policy') return { SpeechController };
    if (name === './voice-commands') return { voiceAudioGate: gate };
    throw new Error(name);
  } });
  return { speech: exports.speech, spoken, modes, gate };
}

test('automatic answers use the configured playback session and resume listening after speech', async () => {
  const { speech, spoken, modes, gate } = setup();
  await speech.answer('A chair is ahead.', 'en');
  assert.equal(modes[0].playsInSilentMode, true);
  assert.equal(modes[0].allowsRecording, false);
  assert.equal(spoken[0].options.useApplicationAudioSession, true);
  assert.equal(gate.paused, true);
  spoken[0].options.onDone();
  assert.equal(gate.paused, false);
});

test('stopping while audio config is pending prevents a delayed answer from speaking', async () => {
  let ready;
  const app = setup(() => new Promise(resolve => { ready = resolve; }));
  const pending = app.speech.answer('Old answer.', 'en');
  for (let i = 0; i < 5; i++) await Promise.resolve();
  assert.equal(app.gate.paused, true);
  await app.speech.stop();
  ready(); await pending;
  assert.equal(app.spoken.length, 0);
  assert.equal(app.gate.paused, false);
});

test('audio setup errors release the microphone gate', async () => {
  const app = setup(async () => { throw new Error('Audio unavailable'); });
  await assert.rejects(app.speech.answer('An answer.', 'en'), /Audio unavailable/);
  assert.equal(app.spoken.length, 0);
  assert.equal(app.gate.paused, false);
});

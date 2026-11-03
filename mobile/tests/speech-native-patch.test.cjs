const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { patchSpeechRecognition } = require('../scripts/patch-speech-recognition.cjs');

test('speech ducking fix is reproducible after installs and retains microphone echo cancellation', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sora-ducking-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'ExpoSpeechRecognizer.swift');
  fs.writeFileSync(file, '        try audioEngine.inputNode.setVoiceProcessingEnabled(true)\n        try audioEngine.outputNode.setVoiceProcessingEnabled(true)\n');
  assert.equal(patchSpeechRecognition(file), true);
  const patched = fs.readFileSync(file, 'utf8');
  assert.match(patched, /setVoiceProcessingEnabled\(true\)/);
  assert.match(patched, /if #available\(iOS 17.0, \*\)/);
  assert.match(patched, /enableAdvancedDucking: false/);
  assert.match(patched, /duckingLevel: \.min/);
  assert.equal(patchSpeechRecognition(file), false);
  assert.equal(fs.readFileSync(file, 'utf8'), patched);
  fs.writeFileSync(file, 'Unrecognized upstream implementation');
  assert.throws(() => patchSpeechRecognition(file), /Unsupported/);
});

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { VoiceAudioGate } = require('../src/lib/voice-commands.ts');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/arabic-recordings.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
function setup() {
  const gate = new VoiceAudioGate(), players = [], exports = {};
  vm.runInNewContext(source, { exports, Error, require(name) {
    if (name.endsWith('.mp3')) {
      assert.ok(fs.statSync(require.resolve('../src/lib/' + name)).size > 1000);
      return name;
    }
    if (name === './voice-commands') return { voiceAudioGate: gate };
    if (name === 'expo-audio') return { createAudioPlayer(asset) {
      const player = { asset, removed: false,
        addListener(_, callback) { this.emit = callback; return { remove() {} }; },
        pause() {}, remove() { this.removed = true; }, play() {},
      };
      players.push(player); return player;
    } };
    throw new Error(name);
  } });
  return { ...exports, gate, players };
}

test('Arabic warnings select bundled female clips and release playback when stopped', () => {
  const app = setup();
  assert.equal(app.arabicAlertRecording('يبدو أن هناك باباً مغلقاً في وسط صورة الكاميرا.'), 'closedDoor');
  app.arabicRecordings.speak('closedDoor', {});
  assert.match(app.players[0].asset, /closed-door.mp3$/);
  assert.equal(app.gate.playing, true);
  app.arabicRecordings.stop();
  assert.equal(app.players[0].removed, true);
  assert.equal(app.gate.playing, false);
});

test('the unavailable notification filters its own echo instead of the missing answer text', () => {
  const app = setup();
  let finished = 0;
  app.arabicRecordings.speak('unavailable', { onDone() { finished++; } });
  assert.match(app.players[0].asset, /unavailable.mp3$/);
  assert.equal(app.gate.userTranscript('الصوت غير متاح حالياً'), '');
  app.players[0].emit({ didJustFinish: true });
  assert.equal(finished, 1);
  assert.equal(app.gate.playing, false);
});

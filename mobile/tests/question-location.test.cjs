const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require('typescript');

function loadLocation() {
  const requests = [];
  const fakeLocation = {
    Accuracy: { Balanced: 3, High: 4 },
    requestForegroundPermissionsAsync: async () => ({ granted: true }),
    getCurrentPositionAsync: async options => {
      requests.push(options);
      return { timestamp: Date.now(), coords: { latitude: 33.89, longitude: 35.5, accuracy: 10 } };
    },
  };
  const filename = require.resolve('../src/lib/question-location.ts');
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mod = new Module(filename, module);
  mod.require = name => name === 'expo-location' ? fakeLocation : require(name);
  mod._compile(compiled, filename);
  return { ...mod.exports, requests };
}

test('trip requests attach accurate GPS even without nearby wording', async () => {
  const { questionLocation, requests } = loadLocation();
  for (const question of ['route to McDonalds', 'start trip to Starbucks', 'give me directions to the hospital', 'how do I get to the pharmacy?', 'itinéraire vers le restaurant', 'ابدأ رحلة إلى ماكدونالدز']) {
    assert.deepEqual(await questionLocation(question), { latitude: 33.89, longitude: 35.5 });
  }
  assert.equal(requests.length, 6);
  assert.ok(requests.every(options => options.accuracy === 4));
});

test('nearby lookups retain balanced GPS and camera questions do not request GPS', async () => {
  const { questionLocation, requests } = loadLocation();
  await questionLocation('what is the nearest restaurant?');
  assert.equal(requests[0].accuracy, 3);
  assert.equal(await questionLocation('Is it safe to walk?'), undefined);
  assert.equal(await questionLocation('Is the route clear?'), undefined);
  assert.equal(requests.length, 1);
});

test('remembered destination followups request fresh accurate GPS', async () => {
  const { questionLocation, requests } = loadLocation();
  for (const question of ['route to there', 'route there', 'take me there', 'directions to it', 'how do I get there?', 'start a trip to that restaurant', "Let's go there", 'itinéraire vers là-bas', 'خذني هناك']) {
    assert.deepEqual(await questionLocation(question), { latitude: 33.89, longitude: 35.5 });
  }
  assert.equal(requests.length, 9);
  assert.ok(requests.every(options => options.accuracy === 4));
});

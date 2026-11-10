const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/lib/emergency.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
function helper(currentLocation) {
  const exports = {};
  vm.runInNewContext(source, { exports, Error, require: () => ({ currentLocation }) });
  return exports.shareSOSLocation;
}

test('SOS reads saved contact, gets a fresh fix, and sends coordinates rather than a client-chosen recipient', async () => {
  const coordinates = { latitude: 33.89, longitude: 35.5, captured_at: '2026-11-10T12:00:00Z', accuracy_meters: 10 };
  const calls = [];
  const share = helper(async highAccuracy => { assert.equal(highAccuracy, true); return coordinates; });
  const message = await share({ request: async (path, method, body) => {
    calls.push({ path, method, body });
    return path.endsWith('/contact') ? { email: 'friend@example.com' } : { message: 'Email submitted' };
  } });
  assert.equal(message, 'Email submitted');
  assert.equal(calls[1].path, '/emergency/location');
  assert.equal(calls[1].method, 'POST');
  assert.equal(calls[1].body, coordinates);
});

test('missing SOS contact prevents GPS access and email submission', async () => {
  let calls = 0;
  const share = helper(async () => assert.fail('GPS should not be requested'));
  await assert.rejects(share({ request: async () => { calls++; return { email: '' }; } }), /Settings/);
  assert.equal(calls, 1);
});

test('location denial and failed delivery are surfaced without announcing success', async () => {
  const denied = helper(async () => { throw new Error('Location denied'); });
  await assert.rejects(denied({ request: async () => ({ email: 'friend@example.com' }) }), /Location denied/);
  const share = helper(async () => ({ latitude: 0, longitude: 0 }));
  await assert.rejects(share({ request: async path => {
    if (path.endsWith('/contact')) return { email: 'friend@example.com' };
    throw new Error('Email delivery unknown');
  } }), /delivery unknown/);
});

test('changing accounts while GPS is loading cancels SOS submission', async () => {
  const api = { tokens: { user: { id: 'original' } }, request: async path => {
    assert.equal(path, '/emergency/contact'); return { email: 'friend@example.com' };
  } };
  const share = helper(async () => { api.tokens = { user: { id: 'different' } }; return { latitude: 0, longitude: 0 }; });
  await assert.rejects(share(api), /Sign-in changed/);
});

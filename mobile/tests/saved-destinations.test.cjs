const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { destinationInput } = require('../src/lib/saved-destinations.ts');

test('coordinate input preserves valid signed values, zero, tiny GPS values, and nickname spacing', () => {
  assert.deepEqual(destinationInput('  My   university ', '-33.89', '35.5'), { nickname: 'My university', latitude: -33.89, longitude: 35.5 });
  assert.equal(destinationInput('home', '0', '0').latitude, 0);
  assert.equal(destinationInput('home', '1e-7', '-180').latitude, 1e-7);
});

test('invalid fields cannot become zero coordinates or an arbitrary destination', () => {
  for (const args of [ ['', '1', '2'], ['...', '1', '2'], ['x'.repeat(81), '1', '2'],
    ['home', '', '2'], ['home', ' ', '2'], ['home', '91', '2'], ['home', '-91', '2'],
    ['home', '1', '181'], ['home', 'NaN', '2'], ['home', 'Infinity', '2'], ['home', '0x10', '2'] ]) {
    assert.throws(() => destinationInput(...args));
  }
});

const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/components/saved-destinations-settings.tsx'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const flush = async () => { for (let i = 0; i < 16; i++) await Promise.resolve(); };

function mount({ initial = [], gps } = {}) {
  const hooks = [], effects = [], cleanups = [], calls = [], alerts = [];
  let cursor = 0, first = true, tree, values = [...initial], nextId = 0;
  const api = { baseUrl: 'https://example.test', tokens: { user: { id: 'owner' } }, async request(path, method = 'GET', body) {
    calls.push({ path, method, body });
    if (method === 'GET') return [...values];
    const id = path.split('/')[2];
    if (method === 'DELETE') { values = values.filter(item => item.id !== id); return; }
    const value = { id: method === 'POST' ? `place-${++nextId}` : id, ...body };
    values = [...values.filter(item => item.id !== id), value];
    return value;
  } };
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  vm.runInNewContext(source + '\nexports.formForTest = SavedDestinationsForm;', { exports, Error, window: {}, require(name) {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
    if (name === 'react') return {
      useState(initial) { const index = cursor++; if (first) hooks[index] = initial; return [hooks[index], value => { hooks[index] = typeof value === 'function' ? value(hooks[index]) : value; }]; },
      useRef(value) { const index = cursor++; if (first) hooks[index] = { current: value }; return hooks[index]; },
      useEffect(fn) { if (first) effects.push(fn); }, useCallback: fn => fn,
    };
    if (name === 'react-native') return { View: 'View', Platform: { OS: 'ios' }, Alert: { alert(...args) { alerts.push(args); } } };
    if (name === 'expo-router') return { useFocusEffect(fn) { if (first) effects.push(fn); } };
    if (name === '@/providers/auth') return { useAuth: () => ({ api, tokens: { user: { id: 'owner' } }, serverUrl: 'https://example.test' }) };
    if (name === '@/providers/preferences') return { usePreferences: () => ({ colors: {} }) };
    if (name === '@/lib/saved-destinations') return { destinationInput };
    if (name === '@/lib/question-location') return { currentLocation: async high => { assert.equal(high, true); return gps ? gps(api) : { latitude: 33.89, longitude: 35.5 }; } };
    if (name === './controls') return { Action: 'Action', Field: 'Field' };
    if (name === './sora-ui') return { Card: 'Card', Label: 'Label' };
    throw new Error(name);
  } });
  function render() { cursor = 0; tree = exports.formForTest(); first = false; return tree; }
  render(); effects.forEach(fn => { const cleanup = fn(); if (cleanup) cleanups.push(cleanup); });
  function nodes(node = tree) {
    if (!node || typeof node !== 'object') return [];
    return [node, ...[node.props?.children].flat(Infinity).flatMap(child => child === undefined ? [] : nodes(child))];
  }
  function field(label) { return nodes().find(node => node.type === 'Field' && node.props.accessibilityLabel === label); }
  return {
    api, calls, alerts, render,
    async ready() { await flush(); render(); },
    input(label, value) { field(label).props.onChangeText(value); render(); },
    value(label) { return field(label).props.value; },
    async press(title) { const node = nodes().find(node => node.type === 'Action' && node.props.title === title); assert.ok(node, title); assert.equal(node.props.disabled, false); node.props.onPress(); await flush(); render(); },
    texts() { return nodes().filter(node => node.type === 'Label').map(node => node.props.children).flat().join(' '); },
    cleanup() { cleanups.forEach(fn => fn()); },
  };
}

test('Settings adds multiple custom nicknames, edits coordinates, and confirms deletion', async () => {
  const app = mount(); await app.ready();
  for (const name of ['home', 'university']) {
    app.input('Destination nickname', name);
    app.input('Destination latitude', '33.89'); app.input('Destination longitude', '35.5');
    await app.press('Save destination');
  }
  assert.match(app.texts(), /home/); assert.match(app.texts(), /university/);
  await app.press('Edit home');
  assert.equal(app.value('Destination nickname'), 'home');
  app.input('Destination latitude', '-12.5');
  await app.press('Save changes');
  assert.deepEqual(app.calls.find(call => call.method === 'PUT').body, { nickname: 'home', latitude: -12.5, longitude: 35.5 });
  await app.press('Delete university');
  assert.equal(app.calls.filter(call => call.method === 'DELETE').length, 0);
  app.alerts[0][2].find(button => button.text === 'Delete').onPress();
  await flush(); app.render();
  assert.equal(app.calls.filter(call => call.method === 'DELETE').length, 1);
  assert.match(app.texts(), /Deleted/);
  app.cleanup();
});

test('invalid coordinates show an error without sending a save request', async () => {
  const app = mount(); await app.ready();
  app.input('Destination nickname', 'home'); app.input('Destination latitude', '99'); app.input('Destination longitude', '35');
  await app.press('Save destination');
  assert.equal(app.calls.filter(call => call.method === 'POST').length, 0);
  assert.match(app.texts(), /Latitude must be/);
  app.cleanup();
});

test('current GPS fills the form but only explicit Save persists it', async () => {
  const app = mount(); await app.ready();
  await app.press('Use my current location');
  assert.equal(app.value('Destination latitude'), '33.89');
  assert.equal(app.calls.length, 1);
  app.input('Destination nickname', 'favorite restaurant');
  await app.press('Save destination');
  assert.equal(app.calls[1].body.nickname, 'favorite restaurant');
  app.cleanup();
});

test('an account change during GPS access cannot populate or save coordinates for the next user', async () => {
  const app = mount({ gps: async api => { api.tokens = { user: { id: 'different' } }; return { latitude: 1, longitude: 2 }; } });
  await app.ready(); await app.press('Use my current location');
  assert.equal(app.value('Destination latitude'), '');
  assert.equal(app.calls.filter(call => call.method === 'POST').length, 0);
  app.cleanup();
});

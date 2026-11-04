const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/providers/preferences.tsx'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

function renderPreferences(saved, initialSystem = 'dark') {
  const states = [];
  const effects = [];
  const nativeAppearance = [];
  const writes = [];
  let cursor = 0;
  let system = initialSystem;
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  vm.runInNewContext(source, { exports, require(name) {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
    if (name === 'react') return {
      createContext: () => ({ Provider: 'PreferencesProvider' }),
      useCallback: fn => fn,
      useContext: () => null,
      useEffect: fn => effects.push(fn),
      useRef: current => ({ current }),
      useState(initial) {
        const index = cursor++;
        if (!(index in states)) states[index] = initial;
        return [states[index], value => { states[index] = typeof value === 'function' ? value(states[index]) : value; }];
      },
    };
    if (name === 'react-native') return { Appearance: { setColorScheme: value => nativeAppearance.push(value) }, Platform: { OS: 'ios' }, useColorScheme: () => system };
    if (name === 'expo-secure-store') return { getItemAsync: async () => saved, setItemAsync: async (_key, value) => { writes.push(JSON.parse(value)); } };
    if (name === 'expo-splash-screen') return { preventAutoHideAsync: async () => {}, hideAsync: async () => {} };
    if (name === 'expo-system-ui') return { setBackgroundColorAsync: async () => {} };
    if (name === 'expo-font') return { useFonts: () => [true, null] };
    if (name === 'expo-status-bar') return { StatusBar: 'StatusBar' };
    if (name === 'expo-navigation-bar') return { NavigationBar: 'NavigationBar' };
    if (name === '../../assets/fonts/Sora.ttf') return 'Sora';
    throw new Error(`Unexpected import: ${name}`);
  } });
  function render() { cursor = 0; effects.length = 0; return exports.PreferencesProvider({ children: 'app' }); }
  function flushEffects() { const pending = effects.splice(0); pending.forEach(effect => effect()); }
  return { render, flushEffects, nativeAppearance, writes, setSystem(value) { system = value; } };
}

test('saved appearance restores before the app is shown and persists later changes', async () => {
  const app = renderPreferences(JSON.stringify({ theme: 'dark', onboarded: true }));
  assert.equal(app.render(), null);
  app.flushEffects();
  await new Promise(resolve => setImmediate(resolve));
  const restored = app.render().props.value;
  assert.equal(restored.preferences.theme, 'dark');
  assert.equal(restored.colors.background, '#0D0703');
  app.flushEffects();
  restored.update({ theme: 'light' });
  const changed = app.render().props.value;
  assert.equal(changed.colors.background, '#FBF2E8');
  app.flushEffects();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.writes.at(-1).theme, 'light');
  assert.equal(app.nativeAppearance.at(-1), 'light');
});

test('System appearance follows operating-system changes', async () => {
  const app = renderPreferences(null, 'dark');
  assert.equal(app.render(), null);
  app.flushEffects();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.render().props.value.colors.background, '#0D0703');
  app.flushEffects();
  assert.equal(app.nativeAppearance.at(-1), 'auto');
  app.setSystem('light');
  assert.equal(app.render().props.value.colors.background, '#FBF2E8');
});

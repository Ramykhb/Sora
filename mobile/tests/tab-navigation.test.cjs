const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const compile = file => ts.transpileModule(fs.readFileSync(require.resolve(file), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const source = compile('../src/components/app-tabs.tsx');
function layout({ platform = 'ios', signedIn = true, onboarded = true, fullscreen = false } = {}) {
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  const NativeTabs = Object.assign(() => {}, { Trigger: Object.assign(() => {}, { Label: 'Label', Icon: 'Icon' }) });
  vm.runInNewContext(source, { exports, require(name) {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
    if (name === 'react') return { useMemo: fn => fn(), useState: () => [fullscreen, () => {}] };
    if (name === 'react-native') return { Platform: { OS: platform }, DynamicColorIOS: value => value };
    if (name === 'expo-router') return { Stack: 'Stack' };
    if (name === 'expo-router/native-tabs') return { NativeTabs };
    if (name === '@/providers/auth') return { useAuth: () => ({ tokens: signedIn ? {} : null }) };
    if (name === '@/providers/preferences') return { palettes: { dark: {}, light: {} }, usePreferences: () => ({ preferences: { onboarded }, colors: { background: '#090B10' } }) };
    if (name === '@/providers/tab-bar') return { TabBarContext: { Provider: 'TabBarProvider' } };
    throw Error(name);
  } });
  const tree = exports.default();
  return platform === 'ios' ? tree.props.children : tree;
}

test('iOS uses system tabs with stable labels and prevents automatic minimization', () => {
  const tabs = layout();
  assert.equal(tabs.props.hidden, false);
  assert.equal(tabs.props.minimizeBehavior, 'never');
  assert.deepEqual(Array.from(tabs.props.children, child => child.props.accessibilityLabel), ['Home', 'Assist', 'History', 'Settings']);
});
test('onboarding, sign-in and full-screen camera capture hide the native bar', () => {
  for (const state of [{ signedIn: false }, { onboarded: false }, { fullscreen: true }]) assert.equal(layout(state).props.hidden, true);
});
test('Android retains the existing page stack and custom navigation', () => {
  assert.equal(layout({ platform: 'android' }).type, 'Stack');
});
test('camera focus owns tab visibility and releases it when leaving the camera', () => {
  const source = compile('../src/providers/tab-bar.tsx');
  const changes = [], effects = [], exports = {};
  vm.runInNewContext(source, { exports, require(name) {
    if (name === 'react') return { createContext: value => value, useContext: () => ({ native: true, setFullscreen: value => changes.push(value) }), useCallback: fn => fn };
    if (name === 'expo-router') return { useFocusEffect: effect => effects.push(effect) };
    throw Error(name);
  } });
  assert.equal(exports.useNativeTabBar(), true);
  exports.useFullscreenTabBar(true);
  const cleanup = effects[0]();
  assert.deepEqual(changes, [true]);
  cleanup();
  assert.deepEqual(changes, [true, false]);
});

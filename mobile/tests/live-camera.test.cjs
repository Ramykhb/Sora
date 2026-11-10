const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const source = ts.transpileModule(
  fs.readFileSync(require.resolve('../src/components/live-camera.native.tsx'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } },
).outputText;

function renderCamera(nativeModules) {
  let imports = 0;
  const rtc = { RTCView: 'RTCView' };
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  vm.runInNewContext(source, {
    exports,
    require(name) {
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === 'react') return {
        useState: initial => [typeof initial === 'function' ? initial() : initial, () => {}],
        useEffect: () => {},
      };
      if (name === 'react-native') return { NativeModules: nativeModules, Text: 'Text', View: 'View' };
      if (name === '@/lib/api') return {};
      if (name === '@/providers/auth') return { useAuth: () => ({ api: {} }) };
      if (name === '@/lib/webrtc') return {};
      if (name === './controls') return { useUI: () => ({}) };
      if (name === 'react-native-webrtc') {
        imports++;
        assert.ok(nativeModules.WebRTCModule, 'must not import WebRTC without its native module');
        return rtc;
      }
      throw new Error(`Unexpected import: ${name}`);
    },
  });
  const view = exports.LiveCamera({ sessionId: 'session', active: true });
  return { imports, message: view.props.children[0].props.children };
}

test('Expo Go and older binaries render guidance without importing WebRTC', () => {
  for (const nativeModules of [{}, { WebRTCModule: null }]) {
    const result = renderCamera(nativeModules);
    assert.equal(result.imports, 0);
    assert.match(result.message, /development build with WebRTC/);
  }
});

test('a binary containing WebRTC loads the native camera implementation', () => {
  const result = renderCamera({ WebRTCModule: {} });
  assert.equal(result.imports, 1);
  assert.equal(result.message, 'Connecting video…');
});

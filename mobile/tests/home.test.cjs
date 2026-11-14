const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/app/(tabs)/(home)/index.tsx'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
function home({ onboarded = true, signedIn = true, screenReader = false, guidance = true, language = 'en' } = {}) {
  const effects = [], navigation = [], spoken = [], spokenLanguages = [];
  let stopped = 0;
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  vm.runInNewContext(source + '\nexports.startHomeForTest = StartStreamHome;', { exports, Date, require(name) {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
    if (name === 'react') return { useRef: current => ({ current }), useCallback: fn => fn, useState: initial => [initial, () => {}] };
    if (name === 'react-native') return { Pressable: 'Pressable', View: 'View', ScrollView: 'ScrollView', Image: 'Image', AccessibilityInfo: { async isScreenReaderEnabled() { return screenReader; } } };
    if (name === '../../assets/images/sora-ribbon.png') return { uri: 'sora-ribbon' };
    if (name === 'react-native-safe-area-context') return { SafeAreaView: 'SafeAreaView' };
    if (name === 'expo-router') return { useFocusEffect: fn => effects.push(fn), router: { navigate: route => navigation.push(route), push: route => navigation.push(route) } };
    if (name === 'expo-linear-gradient') return { LinearGradient: 'LinearGradient' };
    if (name === '@/providers/auth') return { useAuth: () => ({ tokens: signedIn ? {} : null }) };
    if (name === '@/providers/preferences') return { usePreferences: () => ({ colors: {}, preferences: { onboarded, guidance, voiceCommands: true, language } }) };
    if (name === '@/providers/voice-commands') return { useVoiceCommands: () => ({ status: 'Listening.' }) };
    if (name === '@/lib/speech') return { speech: { async answer(text, speechLanguage) { spoken.push(text); spokenLanguages.push(speechLanguage); }, async stop() { stopped++; } } };
    if (name === '@/lib/voice-language') return require('../src/lib/voice-language.ts');
    if (name === '@/components/auth-screen') return { AuthScreen: 'AuthScreen' };
    if (name === '@/components/welcome') return { Welcome: 'Welcome' };
    if (name === '@/components/brand') return { SoraHero: 'SoraHero', SoraLogo: 'SoraLogo' };
    if (name === '@/components/sora-ui') return Object.fromEntries(['BottomNav', 'Icon', 'Label', 'ScreenSafeArea', 'Tap'].map(type => [type, type]));
    throw new Error(name);
  } });
  const entry = exports.default();
  const tree = typeof entry.type === 'function' ? exports.startHomeForTest() : entry;
  const cleanups = effects.map(fn => fn());
  return { tree, navigation, spoken, spokenLanguages, cleanup() { cleanups.forEach(fn => fn?.()); }, get stopped() { return stopped; } };
}

test('the entire home content is one accessible start action and repeated taps create only one navigation', () => {
  const app = home();
  const button = app.tree.props.children[0].props.children;
  assert.equal(button.type, 'Pressable');
  assert.equal(button.props.accessibilityRole, 'button');
  assert.equal(button.props.accessibilityLabel, 'Start live stream');
  assert.match(button.props.accessibilityHint, /camera processing/);
  assert.equal(button.props.style({ pressed: false }).flex, 1);
  assert.equal(button.props.children[1].props.pointerEvents, 'none');
  button.props.onPress(); button.props.onPress();
  assert.equal(app.navigation.length, 1);
  assert.equal(app.navigation[0].pathname, '/camera');
  assert.equal(app.navigation[0].params.mode, 'live');
  assert.ok(app.navigation[0].params.voiceStart);
  app.cleanup();
});

test('tools and navigation sit outside the stream button and do not trigger capture', () => {
  const app = home();
  const footer = app.tree.props.children[1];
  assert.equal(footer.type, 'View');
  footer.props.children[0].props.onPress();
  assert.deepEqual(app.navigation, ['./tools']);
  assert.equal(footer.props.children[1].type, 'BottomNav');
  app.cleanup();
});

test('home still requires onboarding and sign-in before exposing camera startup', () => {
  assert.equal(home({ onboarded: false }).tree.type, 'Welcome');
  assert.equal(home({ signedIn: false }).tree.type, 'AuthScreen');
});

test('spoken home guidance does not speak over an active screen reader', async () => {
  const voiceOver = home({ screenReader: true });
  const regular = home();
  await Promise.resolve(); await Promise.resolve();
  assert.equal(voiceOver.spoken.length, 0);
  assert.match(regular.spoken[0], /Tap anywhere/);
  assert.equal(regular.spokenLanguages[0], 'en-US');
  voiceOver.cleanup(); regular.cleanup();
});

test('spoken home guidance follows the selected language', async () => {
  const french = home({ language: 'fr' });
  const arabic = home({ language: 'ar' });
  await Promise.resolve(); await Promise.resolve();
  assert.match(french.spoken[0], /Touchez n’importe où/);
  assert.equal(french.spokenLanguages[0], 'fr-FR');
  assert.match(arabic.spoken[0], /اضغط في أي مكان/);
  assert.equal(arabic.spokenLanguages[0], 'ar-SA');
  french.cleanup(); arabic.cleanup();
});

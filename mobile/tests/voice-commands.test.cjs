const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { VoiceLevelMeter } = require('../src/lib/voice-level.ts');
const { voiceCommand, voiceInput, VoiceAudioGate } = require('../src/lib/voice-commands.ts');
const { SpeechController } = require('../src/lib/speech-policy.ts');

test('only a wake-prefixed start-stream command controls the app', () => {
  for (const phrase of ['Hey Sora, start stream!', 'HEY SORA START THE STREAM', 'hey sora start stream please']) assert.equal(voiceCommand(phrase), 'start-stream');
  for (const phrase of ['start stream', 'hey sora', 'hello hey sora start stream', 'hey sora do not start stream', 'hey sora start streaming', 'hey sora start stream tomorrow', 'hey sora start stream 123']) assert.equal(voiceCommand(phrase), null);
});

test('Arabic and French wake-word commands match their English actions', () => {
  for (const [action, phrases] of [
    ['start-stream', ['يا سورا ابدأ البث', 'يا سورا، شغّل البث المباشر', 'هي سورا ابدأ البث', 'Hé Sora, démarre le flux', 'Hé Sora lance le direct']],
    ['pause-stream', ['يا سورا أوقف البث مؤقتاً', 'Hé Sora, mets le flux en pause', 'Hé Sora, pause le flux']],
    ['resume-stream', ['يا سورا استأنف البث', 'يا سورا واصل البث', 'Hé Sora, reprends le flux', 'Hé Sora continue le direct']],
    ['stop-stream', ['يا سورا أوقف البث', 'يا سورا أغلق البث', 'Hé Sora, arrête le flux', 'Hé Sora stoppe le direct']],
    ['stop-listening', ['يا سورا توقف عن الاستماع', "Hé Sora, arrête d'écouter", "Hé Sora, arrête l'écoute"]],
    ['start-listening', ['يا سورا ابدأ الاستماع', 'يا سورا استأنف الاستماع', "Hé Sora, commence à écouter", "Hé Sora, reprends l'écoute"]],
    ['mute', ['يا سورا اكتم الصوت', 'يا سورا صامت', 'Hé Sora, coupe le son', 'Hé Sora, mets le son en sourdine']],
    ['unmute', ['يا سورا ألغِ كتم الصوت', 'يا سورا شغّل الصوت', 'Hé Sora, rétablis le son', 'Hé Sora, réactive le son']],
  ]) {
    for (const phrase of phrases) assert.equal(voiceCommand(phrase), action, phrase);
  }
  // The wake word is still required for app controls.
  for (const phrase of ['ابدأ البث', 'démarre le flux', 'أوقف البث', 'arrête le flux']) assert.equal(voiceCommand(phrase), null);
});

test('Arabic and French playback and SOS phrases work without the wake word', () => {
  for (const [action, phrases] of [
    ['repeat-answer', ['أعد الإجابة', 'أعد ما قلته', 'قل ذلك مرة أخرى', 'Répète la réponse', 'Répète ça, s’il te plaît']],
    ['repeat-directions', ['أعد الاتجاهات', 'أعد المسار', 'Répète les directions', "Répète l'itinéraire"]],
    ['stop-speaking', ['توقف عن الكلام', 'أوقف الصوت', 'Arrête de parler', "Arrête l'audio"]],
  ]) {
    for (const phrase of phrases) assert.deepEqual(voiceInput(phrase), { kind: 'command', action }, phrase);
  }
  for (const phrase of ['أرسل موقعي إلى جهة اتصال الطوارئ', 'أرسل رسالة استغاثة', "Envoie ma position à mon contact d'urgence", 'envoie un SOS', 'يا سورا إس أو إس']) {
    assert.deepEqual(voiceInput(phrase), { kind: 'command', action: 'send-sos-location' }, phrase);
  }
  // Unrelated speech in those languages stays a question.
  for (const phrase of ['ما هو هذا', 'أوقف', 'qu’est-ce que c’est', 'répète la question de demain']) {
    assert.equal(voiceInput(phrase)?.kind, 'question', phrase);
  }
});

test('Arabic recognizer spellings and short start commands remain wake-prefixed', () => {
  for (const phrase of ['يا سورا ابدأ', 'يا سورة ابدأ البث', 'يا صورة إبدأ البث', 'هاي سورا بلّش البث', 'ياصورا ابدأ', 'Hey سورا ابدأ البث', 'يا Sora ابدأ البث']) {
    assert.deepEqual(voiceInput(phrase), { kind: 'command', action: 'start-stream' }, phrase);
  }
  assert.equal(voiceCommand('يا سورا وقف البث'), 'stop-stream');
  for (const phrase of ['ابدأ', 'بلش البث', 'يا سورا لا تبدأ البث', 'يا سورا ابدأ رحلة إلى بيروت', 'يا سورا ابدأ البث غداً']) {
    assert.equal(voiceCommand(phrase), null, phrase);
  }
});

test('Arabic speaker echoes match vocalized text without losing user transcript offsets', () => {
  const gate = new VoiceAudioGate();
  gate.playback('اِبْدَأْ البث بقول «يا سُورا، اِبْدَأْ البث».');
  assert.equal(gate.userTranscript('يا سورا ابدأ البث'), '');
  assert.equal(gate.userTranscript('ابدأ البث بقول ما الذي أمامي'), 'ما الذي أمامي');
  assert.equal(gate.userTranscript('يا سورا أوقف البث'), 'يا سورا أوقف البث');
});

test('listening stays paused until every audio user releases it', () => {
  const gate = new VoiceAudioGate();
  const states = [];
  const unsubscribe = gate.subscribe(() => states.push(gate.paused));
  const speech = gate.suspend();
  const recording = gate.suspend();
  speech(); speech();
  assert.equal(gate.paused, true);
  recording();
  assert.equal(gate.paused, false);
  assert.deepEqual(states, [true, true, true, false]);
  unsubscribe(); gate.suspend();
  assert.equal(states.length, 4);
});

const providerSource = ts.transpileModule(fs.readFileSync(require.resolve('../src/providers/voice-commands.tsx'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
function mount({ native = true, granted = true, permissionPromise, enabled = true, questionsEnabled = true, language = 'en' } = {}) {
  const effects = [], cleanups = [], listeners = new Map(), navigation = [], starts = [], spoken = [], spokenLanguages = [], statuses = [], timers = new Map();
  const preferences = { speak: true, onboarded: true, voiceCommands: enabled, handsFreeQuestions: questionsEnabled, language };
  const preferenceUpdates = [];
  const sosCalls = [];
  const gate = new VoiceAudioGate();
  const meter = new VoiceLevelMeter();
  const appState = { currentState: 'active', addEventListener: () => ({ remove() {} }) };
  let imports = 0, aborts = 0, stops = 0, speechStops = 0, now = 10000;
  const speech = new SpeechController({
    async stop() { speechStops++; },
    speak(text, options) { spoken.push(text); spokenLanguages.push(options.language); },
  });
  const recognizer = {
    isRecognitionAvailable: () => true,
    requestPermissionsAsync: () => permissionPromise || Promise.resolve({ granted }),
    start(options) { starts.push(options); },
    abort() { aborts++; },
    stop() { stops++; },
    addListener(name, fn) { listeners.set(name, fn); return { remove() { listeners.delete(name); } }; },
  };
  const exports = {};
  vm.runInNewContext(providerSource, {
    exports, Error, Date: { now: () => now },
    setTimeout(fn) { const id = Symbol(); timers.set(id, fn); return id; }, clearTimeout(id) { timers.delete(id); },
    require(name) {
      if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }) };
      if (name === 'react') return {
        useCallback: fn => fn,
        createContext: value => ({ Provider: 'Provider', value }), useContext: ctx => ctx.value,
        useRef: current => ({ current }), useEffect: fn => effects.push(fn),
        useState: initial => [typeof initial === 'function' ? initial() : initial, value => statuses.push(value)],
      };
      if (name === 'react-native') return { Platform: { OS: 'ios' }, AppState: appState, AccessibilityInfo: { announceForAccessibility() {} } };
      if (name === 'expo') return { requireOptionalNativeModule: () => native ? {} : null };
      if (name === 'expo-router') return { router: { navigate: route => navigation.push(route) } };
      if (name === './auth') return { useAuth: () => ({ ready: true, tokens: {} }) };
      if (name === './preferences') return { usePreferences: () => ({ preferences, update(value) { preferenceUpdates.push(value); Object.assign(preferences, value); } }) };
      if (name === '@/lib/emergency') return { shareSOSLocation: async () => { sosCalls.push(true); return 'Your location email was submitted to your SOS contact.'; } };
      if (name === '@/lib/voice-level') return { voiceLevel: meter };
      if (name === '@/lib/voice-commands') return { voiceAudioGate: gate, voiceInput };
      if (name === '@/lib/voice-language') return { ...require('../src/lib/voice-language.ts'), voiceLanguage: () => 'en' };
      if (name === '@/lib/speech') return { speech };
      if (name === '@/lib/server-speech') return { serverSpeech: { configure: () => () => {} } };
      if (name === 'expo-speech-recognition') { imports++; assert.equal(native, true); return { ExpoSpeechRecognitionModule: recognizer }; }
      throw new Error(`Unexpected import ${name}`);
    },
  });
  const view = exports.VoiceCommandsProvider({ children: null });
  effects.forEach(fn => { const cleanup = fn(); if (cleanup) cleanups.push(cleanup); });
  return {
    navigation, starts, spoken, spokenLanguages, statuses, sosCalls, gate, appState, view, imports, preferenceUpdates, preferences, meter, speech,
    get stops() { return stops; },
    get speechStops() { return speechStops; },
    get aborts() { return aborts; },
    emit: (name, event) => listeners.get(name)?.(event),
    tick() { const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn()); now += 1000; },
    cleanup() { cleanups.forEach(fn => fn()); },
  };
}
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

test('explicit repeat and stop-speaking commands work with or without the wake phrase', () => {
  for (const [action, phrases] of [
    ['repeat-answer', ['Repeat that', 'say that again', 'Hey Sora, repeat the last answer please']],
    ['repeat-directions', ['repeat the directions', 'repeat directions', 'Hey Sora, repeat my route please']],
    ['stop-speaking', ['stop speaking', 'Stop talking please', 'Hey Sora, stop audio']],
  ]) {
    for (const phrase of phrases) {
      assert.equal(voiceCommand(phrase), action);
      assert.deepEqual(voiceInput(phrase), { kind: 'command', action });
    }
  }
  for (const phrase of ['stop', 'repeat', 'do not stop speaking', 'How do I repeat that?', 'repeat the directions to McDonalds', 'Hey Sora repeat that tomorrow']) {
    assert.equal(voiceCommand(phrase), null);
  }
});

test('repeat replays the exact last reply and language without sending another question', async () => {
  const app = mount(), questions = [];
  app.view.props.value.registerQuestions(async question => {
    questions.push(question);
    return { answer: 'Une porte est visible.', language: 'fr' };
  });
  await flush(); app.tick();
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('what is in front of me');
  await say('Hey Sora repeat that');
  assert.deepEqual(questions, ['what is in front of me']);
  assert.deepEqual(app.spoken, ['Une porte est visible.', 'Une porte est visible.']);
  assert.deepEqual(app.spokenLanguages, ['fr', 'fr']);
  app.cleanup();
});

test('repeat directions retains the route after a camera answer and app confirmation', async () => {
  const app = mount(), questions = [];
  const route = 'Cafe is approximately 500 m away on foot. Walking directions from Google Maps:\n1. Head north (100 m).\n2. Turn right (400 m).';
  app.view.props.value.registerQuestions(async question => {
    questions.push(question);
    return { answer: questions.length === 1 ? route : 'A chair is visible.', language: 'en' };
  });
  await flush(); app.tick();
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('start trip to the nearest cafe');
  await say('what is in front of me');
  await say('hey sora unmute');
  await say('repeat the directions');
  assert.equal(app.spoken.at(-1), route);
  assert.equal(questions.length, 2);
  assert.equal(app.preferenceUpdates.length, 1);
  app.cleanup();
});

test('missing replay content gives guidance and never becomes a backend question', async () => {
  const app = mount(), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  await flush(); app.tick();
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('repeat that');
  assert.match(app.spoken.at(-1), /no answer to repeat/);
  await say('repeat the directions');
  assert.match(app.spoken.at(-1), /no directions to repeat/);
  await say('say that again');
  assert.match(app.spoken.at(-1), /no answer to repeat/);
  assert.equal(questions.length, 0);
  app.cleanup();
});

test('stop speaking silences pending answers without muting, changing the stream, or disabling questions', async () => {
  const app = mount(), controls = [];
  let resolve;
  app.view.props.value.registerStream(async command => { controls.push(command); return 'Unexpected'; });
  app.view.props.value.registerQuestions(() => new Promise(done => { resolve = done; }));
  await flush(); app.tick();
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('describe the scene');
  await say('stop speaking');
  resolve({ answer: 'Delayed answer must stay silent.', language: 'en' }); await flush();
  assert.equal(app.spoken.length, 0);
  assert.equal(await app.speech.repeatLastAnswer(), false);
  assert.equal(app.preferences.handsFreeQuestions, true);
  assert.equal(app.preferences.speak, true);
  assert.deepEqual(controls, []);
  assert.equal(app.preferenceUpdates.length, 0);
  assert.ok(app.speechStops > 0);
  app.view.props.value.registerQuestions(async () => ({ answer: 'A fresh answer.', language: 'en' }));
  await say('what is ahead');
  assert.equal(app.spoken.at(-1), 'A fresh answer.');
  app.cleanup();
});

test('a stop command cancels a repeat still waiting to stop previous audio', async () => {
  const app = mount();
  await flush(); app.tick();
  app.speech.rememberAnswer('An earlier answer.', 'en');
  const stop = app.speech.stop.bind(app.speech);
  let release, stops = 0;
  app.speech.stop = async () => {
    await stop();
    if (++stops === 1) await new Promise(done => { release = done; });
  };
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('repeat that');
  await say('stop speaking');
  release(); await flush();
  assert.equal(app.spoken.length, 0);
  app.cleanup();
});

test('replay works while questions or the stream are paused and still respects mute', async () => {
  const app = mount({ questionsEnabled: false }), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  app.view.props.value.registerStream(async () => 'Unexpected', () => true);
  await flush(); app.tick();
  app.speech.rememberAnswer('The last answer.', 'en');
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('repeat that');
  assert.equal(app.spoken.at(-1), 'The last answer.');
  await say('hey sora mute');
  const count = app.spoken.length;
  await say('say that again');
  assert.equal(app.spoken.length, count);
  assert.ok(app.statuses.some(value => typeof value === 'string' && /Voice is muted/.test(value)));
  assert.equal(questions.length, 0);
  app.cleanup();
});

test('cleanup clears replay history and rejects a reply arriving after logout or unmount', async () => {
  const app = mount();
  let resolve;
  app.view.props.value.registerQuestions(() => new Promise(done => { resolve = done; }));
  await flush(); app.tick();
  app.speech.rememberAnswer('Previous private answer.', 'en');
  app.emit('result', { results: [{ transcript: 'describe the scene' }], isFinal: true });
  app.cleanup();
  resolve({ answer: 'Late private answer.', language: 'en' }); await flush();
  assert.equal(app.spoken.length, 0);
  assert.equal(await app.speech.repeatLastAnswer(), false);
});

test('speaker echoes of playback commands cannot trigger replay or stop speech', async () => {
  const app = mount();
  await flush(); app.tick();
  const release = app.gate.playback('You can say repeat that, repeat the directions, or stop speaking.');
  for (const transcript of ['repeat that', 'repeat the directions', 'stop speaking']) {
    app.emit('result', { results: [{ transcript }], isFinal: true });
  }
  await flush();
  assert.equal(app.spoken.length, 0);
  assert.equal(app.speechStops, 0);
  release(); app.cleanup();
});

test('recognizer restarts after silence and ignores unrelated speech, duplicates, audio playback and background commands', async () => {
  const app = mount();
  await flush(); app.tick();
  assert.equal(app.starts.length, 1);
  assert.equal(app.starts[0].continuous, true);
  assert.equal(app.starts[0].recordingOptions.persist, false);
  const result = text => app.emit('result', { results: [{ transcript: text }], isFinal: true });
  result('start stream'); assert.equal(app.navigation.length, 0);
  result('Hey Sora start stream'); result('Hey Sora start stream');
  assert.equal(app.navigation.length, 1);
  assert.equal(app.navigation[0].pathname, '/camera');
  assert.equal(app.navigation[0].params.mode, 'live');
  app.emit('end'); app.tick(); assert.equal(app.starts.length, 2);
  const release = app.gate.suspend();
  for (let i = 0; i < 5; i++) app.tick();
  result('Hey Sora start stream'); assert.equal(app.navigation.length, 1);
  release(); app.appState.currentState = 'background';
  result('Hey Sora start stream'); assert.equal(app.navigation.length, 1);
  app.cleanup();
  const previous = app.starts.length;
  app.tick(); assert.equal(app.starts.length, previous);
  assert.ok(app.aborts > 0);
});

test('denied permissions do not start recognition or cause retry loops', async () => {
  const app = mount({ granted: false });
  await flush(); app.tick();
  assert.equal(app.starts.length, 0);
  assert.ok(app.statuses.some(value => typeof value === 'string' && /Allow microphone/.test(value)));
  app.emit('end'); app.tick(); assert.equal(app.starts.length, 0);
  app.cleanup();
});

test('unmounting while permissions are pending cannot start a listener later', async () => {
  let resolve;
  const app = mount({ permissionPromise: new Promise(done => { resolve = done; }) });
  app.cleanup(); resolve({ granted: true });
  await flush(); app.tick();
  assert.equal(app.starts.length, 0);
});

test('the selected language drives recognition and spoken feedback', async () => {
  const app = mount({ language: 'fr' });
  await flush(); app.tick();
  assert.equal(app.starts[0].lang, 'fr-FR');
  app.emit('result', { results: [{ transcript: 'décris la scène' }], isFinal: true });
  await flush();
  assert.match(app.spoken.at(-1), /Démarrez d’abord un flux/);
  assert.equal(app.spokenLanguages.at(-1), 'fr-FR');
  app.cleanup();
});

test('Arabic recognition routes a short start command to the live camera', async () => {
  const app = mount({ language: 'ar' });
  await flush(); app.tick();
  assert.equal(app.starts[0].lang, 'ar-SA');
  assert.ok(app.starts[0].contextualStrings.includes('يا سورا ابدأ'));
  app.emit('result', { results: [{ transcript: 'يا صورة، إبدأ' }], isFinal: true });
  assert.equal(app.navigation.length, 1);
  assert.equal(app.navigation[0].pathname, '/camera');
  assert.equal(app.navigation[0].params.mode, 'live');
  app.cleanup();
});

test('Arabic full start command accepts a recognizer spelling of Sora as Sarah', async () => {
  const app = mount({ language: 'ar' });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'يا سارة ابدأ البث' }], isFinal: true });
  assert.equal(app.navigation.length, 1);
  app.cleanup();
});

test('an unmatched Arabic wake command can use a supported stream alternative', async () => {
  const app = mount({ language: 'ar' });
  await flush(); app.tick();
  assert.equal(app.starts[0].maxAlternatives, 5);
  app.emit('result', { results: [{ transcript: 'يا سورا ابدأ البحث' }, { transcript: 'يا سورا ابدأ البث' }], isFinal: true });
  assert.equal(app.navigation.length, 1);
  app.cleanup();
});

test('recognition alternatives cannot replace questions or speaker echoes with stream commands', async () => {
  for (const echo of [false, true]) {
    const app = mount({ language: 'ar' });
    await flush(); app.tick();
    const primary = echo ? 'يا سورا ابدأ البث' : 'ما الذي أمامي';
    if (echo) app.gate.playback(primary);
    app.emit('result', { results: [{ transcript: primary }, { transcript: 'يا سورا ابدأ البث' }], isFinal: true });
    assert.equal(app.navigation.length, 0);
    app.cleanup();
  }
});

test('unmatched commands show the actual transcript for troubleshooting', async () => {
  const app = mount({ language: 'ar' });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'يا سورا ابدأ البحث' }], isFinal: true });
  assert.ok(app.statuses.includes('Unrecognized Sora command: “يا سورا ابدأ البحث”'));
  assert.equal(app.navigation.length, 0);
  app.cleanup();
});

test('old native builds and disabled voice commands leave the app usable', async () => {
  const old = mount({ native: false });
  assert.equal(old.imports, 0);
  assert.match(old.view.props.value.status, /new development build/);
  old.cleanup();
  const disabled = mount({ enabled: false });
  await flush(); disabled.tick(); assert.equal(disabled.starts.length, 0);
  disabled.cleanup();
});


const cameraSource = ts.transpileModule(fs.readFileSync(require.resolve('../src/app/(tabs)/camera.tsx'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
async function voiceStartCamera(granted, { active = false, paused = false, question, command, closeError, language = 'en', event, detectionEnabled = true, toggleDetection, detectionError } = {}) {
  const effects = [], requests = [], spoken = [], updates = [], alerts = [], sessionUpdates = [];
  const session = { id: 'voice-session', status: 'active', language: 'en', alerts_enabled: detectionEnabled };
  const reply = { answer: 'A chair beside a table.', language: 'en' };
  let voiceQuestion, voiceControl, liveEvent, stateIndex = 0;
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  vm.runInNewContext(cameraSource + '\nexports.captureForTest = Capture;', {
    exports, setTimeout, clearTimeout, Error,
    require(name) {
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === 'react') return {
        useState: initial => { const index = stateIndex++; return [active && index === 0 ? session : active && index === 8 ? true : index === 12 ? paused : initial, value => { updates.push(value); if (index === 0) sessionUpdates.push(value); }]; }, useRef: current => ({ current }),
        useCallback: fn => fn, useEffect: fn => effects.push(fn), useSyncExternalStore: (_, snapshot) => snapshot(),
      };
      if (name === 'react-native') return { AppState: { currentState: 'active', addEventListener: () => ({ remove() {} }) }, StyleSheet: { create: value => value }, Platform: { OS: 'ios' } };
      if (name === '@/providers/tab-bar') return { useFullscreenTabBar() {} };
      if (name === 'expo-camera') return { useCameraPermissions: () => [null, async () => ({ granted })] };
      if (name === 'expo-router') return { useFocusEffect() {}, useLocalSearchParams: () => ({ mode: 'live', voiceStart: '123' }) };
      if (name === '@/providers/voice-commands') return { useHandsFreeQuestions(handler) { voiceQuestion = handler; }, useVoiceStreamControls(handler) { voiceControl = handler; }, useVoiceCommands: () => ({ status: '' }) };
      if (name === '@/providers/auth') return { useAuth: () => ({ api: { async request(...args) { requests.push(args); if (args[0].endsWith('/close') && closeError) throw closeError; if (args[1] === 'PATCH') { if (detectionError) throw detectionError; return { ...session, ...args[2] }; } return args[0].endsWith('/questions') ? reply : session; } } }) };
      if (name === '@/providers/preferences') return { usePreferences: () => ({ colors: {}, preferences: { guidance: false, language } }) };
      if (name === '@/lib/voice-language') return { ...require('../src/lib/voice-language.ts'), voiceLanguage: () => 'en' };
      if (name === '@/lib/speech') return { speech: { async answer(text) { spoken.push(text); }, async stop() {}, async alert(...args) { alerts.push(args); }, getRoutePlayback: () => null, subscribeRoute: () => () => {} } };
      if (name === '@/lib/live') return { connectLive: (_, path, handler) => { liveEvent = handler; return { close() {} }; } };
      if (name === '@/lib/camera-feedback') return { cameraFeedback: () => null };
      if (name === '@/lib/question-location') return { questionLocation: async () => ({ latitude: 33.89, longitude: 35.5 }) };
      return {};
    },
  });
  const view = exports.captureForTest();
  const cleanups = effects.map(fn => fn());
  await flush(); await flush();
  // React effects may run again: one voice request must create only one session.
  effects.forEach(fn => fn());
  await flush();
  if (event) liveEvent?.(event);
  if (typeof toggleDetection === 'boolean') {
    const findSwitch = node => {
      if (!node || typeof node !== 'object') return null;
      if (Array.isArray(node)) return node.map(findSwitch).find(Boolean);
      if (node.props?.accessibilityLabel === 'Detect obstacles') return node;
      return findSwitch(node.props?.children);
    };
    const toggle = findSwitch(view);
    assert.ok(toggle, 'The live camera must expose Detect obstacles');
    assert.equal(toggle.props.value, detectionEnabled);
    toggle.props.onValueChange(toggleDetection);
    await flush(); await flush();
  }
  const askedReply = question ? await voiceQuestion(question) : null;
  let controlReply, controlError;
  try { if (command) controlReply = await voiceControl(command); } catch (error) { controlError = error; }
  cleanups.forEach(fn => { if (typeof fn === 'function') fn(); });
  return { requests, spoken, updates, alerts, sessionUpdates, session, askedReply, controlReply, controlError };
}

test('a voice start requests camera permission and creates exactly one streaming session without taps', async () => {
  const app = await voiceStartCamera(true);
  assert.equal(app.requests.length, 1);
  assert.equal(app.requests[0][0], '/sessions');
  assert.equal(app.requests[0][1], 'POST');
  assert.equal(app.requests[0][2].consent, true);
  assert.equal(app.requests[0][2].alerts_enabled, true);
  assert.ok(app.updates.includes(app.session));
  assert.ok(app.spoken.includes('Starting your stream.'));
});

test('a camera session uses the selected language for answers', async () => {
  const app = await voiceStartCamera(true, { language: 'ar' });
  assert.equal(app.requests[0][2].language, 'ar');
  assert.ok(app.spoken.includes('جارٍ بدء البث.'));
});

test('denied camera permission is spoken and never creates a streaming session', async () => {
  const app = await voiceStartCamera(false);
  assert.equal(app.requests.length, 0);
  assert.ok(app.spoken.some(text => /Camera access is required/.test(text)));
});


test('all Hey Sora prefixes stay reserved, including future commands', () => {
  for (const phrase of ['Hey Sora zoom in', 'hey sora', 'Hey, Sora: describe the scene', 'HEY SORA turn up the volume']) {
    assert.equal(voiceInput(phrase).kind, 'command');
    assert.equal(voiceInput(phrase).action, null);
  }
  assert.deepEqual(voiceInput('Describe the scene'), { kind: 'question', question: 'Describe the scene' });
  assert.deepEqual(voiceInput('What is in front of me?'), { kind: 'question', question: 'What is in front of me?' });
  assert.equal(voiceInput('  '), null);
});

test('partial questions wait for finalization, then submit once and speak the answer', async () => {
  const app = mount();
  const questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'A chair is in front of you.', language: 'en' }; });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'describe the' }], isFinal: false });
  assert.equal(questions.length, 0);
  app.tick(); assert.equal(app.stops, 1);
  assert.equal(questions.length, 0);
  app.emit('result', { results: [{ transcript: 'describe the scene' }], isFinal: true });
  app.emit('result', { results: [{ transcript: 'describe the scene' }], isFinal: true });
  await flush();
  assert.deepEqual(questions, ['describe the scene']);
  assert.deepEqual(app.spoken, ['A chair is in front of you.']);
  app.cleanup();
});

test('unknown commands never reach the question handler', async () => {
  const app = mount();
  const questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'Hey Sora describe the scene' }], isFinal: true });
  await flush();
  assert.equal(questions.length, 0);
  assert.equal(app.navigation.length, 0);
  assert.match(app.spoken[0], /not available yet/);
  app.cleanup();
});

test('questions without a session receive spoken startup guidance', async () => {
  const app = mount(); await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'describe the scene' }], isFinal: true });
  await flush();
  assert.match(app.spoken[0], /Start a stream first/);
  app.cleanup();
});

test('only one question runs at a time and replies from a previous screen are discarded', async () => {
  const app = mount();
  let resolve;
  const questions = [];
  const unregister = app.view.props.value.registerQuestions(question => { questions.push(question); return new Promise(done => { resolve = done; }); });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'what is in front of me' }], isFinal: true });
  app.emit('result', { results: [{ transcript: 'describe the scene' }], isFinal: true });
  assert.equal(questions.length, 1);
  unregister(); resolve({ answer: 'An old answer', language: 'en' });
  await flush();
  assert.equal(app.spoken.length, 0);
  app.cleanup();
});

test('question errors are spoken and listening can accept the next question', async () => {
  const app = mount();
  app.view.props.value.registerQuestions(async () => { throw new Error('The server is unavailable. Try again.'); });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'describe the scene' }], isFinal: true });
  await flush();
  assert.match(app.spoken[0], /server is unavailable/);
  app.view.props.value.registerQuestions(async () => ({ answer: 'A table.', language: 'en' }));
  app.emit('result', { results: [{ transcript: 'what is here' }], isFinal: true });
  await flush(); assert.equal(app.spoken[1], 'A table.');
  app.cleanup();
});


test('describe the scene uses the live session question endpoint without navigating away or capturing with a button', async () => {
  const app = await voiceStartCamera(true, { active: true, question: 'describe the scene' });
  assert.equal(app.requests.length, 1);
  assert.equal(app.requests[0][0], '/sessions/voice-session/questions');
  assert.equal(app.requests[0][1], 'POST');
  assert.equal(app.requests[0][2].question, 'describe the scene');
  assert.equal(app.requests[0][2].scope, 'recent');
  assert.equal(app.requests[0][2].language, 'en');
  assert.equal(app.askedReply.answer, 'A chair beside a table.');
  assert.ok(app.updates.includes('A chair beside a table.'));
});


test('a hands-free route question includes the current location for saved destinations', async () => {
  const app = await voiceStartCamera(true, { active: true, question: 'start route home' });
  assert.equal(app.requests[0][0], '/sessions/voice-session/questions');
  assert.deepEqual(app.requests[0][2].location, { latitude: 33.89, longitude: 35.5 });
  assert.equal(app.requests[0][2].question, 'start route home');
});

test('stream controls require a complete Hey Sora command', () => {
  for (const action of ['pause', 'resume', 'stop']) {
    assert.equal(voiceCommand(`Hey Sora ${action} stream`), `${action}-stream`);
    assert.equal(voiceCommand(`HEY SORA, ${action.toUpperCase()} THE STREAM PLEASE!`), `${action}-stream`);
    for (const phrase of [`${action} stream`, `hey sora do not ${action} stream`, `hey sora ${action} stream tomorrow`]) assert.equal(voiceCommand(phrase), null);
  }
});

test('pause, resume and stop dispatch to stream controls and never become questions', async () => {
  const app = mount(), controls = [], questions = [];
  app.view.props.value.registerStream(async command => { controls.push(command); return 'Stream command confirmed.'; });
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  await flush(); app.tick();
  for (const action of ['pause', 'resume', 'stop']) {
    const event = { results: [{ transcript: `hey sora ${action} stream` }], isFinal: true };
    app.emit('result', event); app.emit('result', event);
    await flush();
  }
  assert.deepEqual(controls, ['pause-stream', 'resume-stream', 'stop-stream']);
  assert.equal(questions.length, 0);
  assert.equal(app.navigation.length, 0);
  assert.equal(app.spoken.length, 3);
  app.cleanup();
});

test('stream controls give spoken guidance when no stream is open', async () => {
  const app = mount(); await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'hey sora resume stream' }], isFinal: true });
  await flush(); assert.match(app.spoken[0], /no stream open/);
  app.cleanup();
});

test('closing a session can unregister its controls and still receive spoken confirmation', async () => {
  const app = mount();
  const unregister = app.view.props.value.registerStream(async () => { unregister(); return 'Stream stopped.'; });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'hey sora stop stream' }], isFinal: true });
  await flush(); assert.equal(app.spoken[0], 'Stream stopped.');
  app.cleanup();
});

test('stream controls survive other screen registrations and restore the previous open session', async () => {
  const app = mount(), controls = [];
  app.view.props.value.registerStream(async command => { controls.push(command); return 'Stream paused.'; });
  const unregister = app.view.props.value.registerStream(async () => 'Other session');
  unregister();
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'hey sora pause stream' }], isFinal: true });
  await flush(); assert.deepEqual(controls, ['pause-stream']);
  app.cleanup();
});

test('camera pause and resume keep the same server session', async () => {
  const paused = await voiceStartCamera(true, { active: true, command: 'pause-stream' });
  assert.equal(paused.requests.length, 0);
  assert.match(paused.controlReply, /Stream paused/);
  const resumed = await voiceStartCamera(true, { active: true, paused: true, command: 'resume-stream' });
  assert.equal(resumed.requests.length, 0);
  assert.match(resumed.controlReply, /Resuming/);
  assert.ok(resumed.updates.includes(false));
});

test('camera stop closes capture without deleting saved moments', async () => {
  const app = await voiceStartCamera(true, { active: true, command: 'stop-stream' });
  assert.equal(app.requests.length, 1);
  assert.equal(app.requests[0][0], '/sessions/voice-session/close');
  assert.equal(app.requests[0][1], 'POST');
  assert.ok(app.sessionUpdates.includes(null));
  assert.match(app.controlReply, /Stream stopped/);
});

test('failed session closure keeps the camera paused and propagates the error for spoken feedback', async () => {
  const failure = new Error('Server unavailable.');
  const app = await voiceStartCamera(true, { active: true, command: 'stop-stream', closeError: failure });
  assert.equal(app.controlError, failure);
  assert.equal(app.sessionUpdates.includes(null), false);
  assert.ok(app.updates.includes(true));
});


test('listening controls require Hey Sora and allow start/resume aliases', () => {
  assert.equal(voiceCommand('Hey Sora, stop listening please'), 'stop-listening');
  assert.equal(voiceCommand('hey sora start listening'), 'start-listening');
  assert.equal(voiceCommand('hey sora resume listening'), 'start-listening');
  for (const text of ['stop listening', 'hey sora do not stop listening', 'hey sora stop listening tomorrow']) assert.equal(voiceCommand(text), null);
});

test('stop listening ignores conversation silently, retains app commands, and start listening restores questions', async () => {
  const app = mount(), questions = [], controls = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'A chair.', language: 'en' }; });
  app.view.props.value.registerStream(async command => { controls.push(command); return 'Command confirmed.'; });
  await flush(); app.tick();
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('hey sora stop listening');
  assert.equal(app.preferences.handsFreeQuestions, false);
  const confirmations = app.spoken.length;
  await say('describe the scene'); await say('how was your day');
  assert.equal(questions.length, 0); assert.equal(app.spoken.length, confirmations);
  await say('hey sora resume stream');
  assert.deepEqual(controls, ['resume-stream']);
  await say('what is around me'); assert.equal(questions.length, 0);
  await say('hey sora start listening');
  assert.equal(app.preferences.handsFreeQuestions, true);
  await say('what is ahead'); assert.deepEqual(questions, ['what is ahead']);
  app.cleanup();
});

test('a paused stream ignores ordinary speech without errors, while Hey Sora resume restores questions', async () => {
  const app = mount(), questions = [];
  let paused = true;
  app.view.props.value.registerStream(async command => { paused = command !== 'resume-stream'; return 'Stream resumed.'; }, () => paused);
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'A table.', language: 'en' }; });
  await flush(); app.tick();
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('describe the scene'); await say('hello friend');
  assert.equal(questions.length, 0); assert.equal(app.spoken.length, 0);
  await say('hey sora resume stream');
  await say('what is here'); assert.deepEqual(questions, ['what is here']);
  app.cleanup();
});

test('manual pause updates block speech across screens and start listening does not override a paused stream', async () => {
  const app = mount(), questions = [];
  let paused = false;
  app.view.props.value.registerStream(async () => 'Confirmed.', () => paused);
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Answer', language: 'en' }; });
  await flush(); app.tick();
  paused = true; app.view.props.value.refreshStreamState();
  app.emit('result', { results: [{ transcript: 'hey sora start listening' }], isFinal: true }); await flush();
  assert.match(app.spoken[0], /Resume your stream/);
  app.emit('result', { results: [{ transcript: 'describe the scene' }], isFinal: true }); await flush();
  assert.equal(questions.length, 0); assert.equal(app.spoken.length, 1);
  app.cleanup();
});

test('stop listening cancels pending spoken replies and re-enabling can ask immediately', async () => {
  const app = mount();
  let resolve;
  app.view.props.value.registerQuestions(() => new Promise(done => { resolve = done; }));
  await flush(); app.tick();
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('what is nearby');
  await say('hey sora stop listening');
  await say('hey sora start listening');
  resolve({ answer: 'Old answer that should stay silent.', language: 'en' }); await flush();
  assert.ok(!app.spoken.includes('Old answer that should stay silent.'));
  app.view.props.value.registerQuestions(async () => ({ answer: 'Fresh answer.', language: 'en' }));
  await say('what is new');
  assert.equal(app.spoken.at(-1), 'Fresh answer.');
  app.cleanup();
});

test('saved commands-only preference ignores questions immediately after launch and permits Hey Sora commands', async () => {
  const app = mount({ questionsEnabled: false }), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'describe the scene' }], isFinal: true }); await flush();
  assert.equal(questions.length, 0); assert.equal(app.spoken.length, 0);
  app.emit('result', { results: [{ transcript: 'hey sora start stream' }], isFinal: true }); await flush();
  assert.equal(app.navigation.length, 1);
  app.cleanup();
});


test('answer playback keeps the microphone available, ignores echoes, and preserves exclusive recording', () => {
  const gate = new VoiceAudioGate();
  const release = gate.playback('There is a blue chair near the table.');
  assert.equal(gate.paused, false);
  assert.equal(gate.playing, true);
  assert.equal(gate.userTranscript('a blue chair'), '');
  assert.equal(gate.userTranscript('What is beside it?'), 'What is beside it?');
  assert.equal(gate.userTranscript('blue chair near the table hey sora pause stream'), 'hey sora pause stream');
  const recorded = gate.suspend();
  assert.equal(gate.paused, true);
  release();
  assert.equal(gate.playing, false);
  assert.equal(gate.paused, true);
  recorded(); assert.equal(gate.paused, false);
});

test('speaking interrupts an answer on a partial result while the complete question is still accepted', async () => {
  const app = mount(), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Beside the window.', language: 'en' }; });
  await flush(); app.tick();
  const release = app.gate.playback('There is a blue chair near the table.');
  assert.equal(app.starts[0].iosVoiceProcessingEnabled, true);
  assert.equal(app.starts[0].iosCategory.mode, 'voiceChat');
  const aborts = app.aborts;
  app.emit('result', { results: [{ transcript: 'What is beside' }], isFinal: false });
  await flush();
  assert.equal(app.speechStops, 1);
  assert.equal(app.aborts, aborts, 'interrupting speech must keep the current recognition session');
  assert.equal(questions.length, 0);
  release();
  app.emit('result', { results: [{ transcript: 'What is beside the chair?' }], isFinal: true });
  await flush();
  assert.deepEqual(questions, ['What is beside the chair?']);
  assert.equal(app.spoken.at(-1), 'Beside the window.');
  app.cleanup();
});

test('speaker echoes do not interrupt or execute commands, including delayed final results', async () => {
  const app = mount(), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  await flush(); app.tick();
  const release = app.gate.playback('Say Hey Sora stop listening to chat freely.');
  for (const final of [false, true]) app.emit('result', { results: [{ transcript: 'Hey Sora stop listening' }], isFinal: final });
  assert.equal(app.speechStops, 0);
  assert.equal(app.preferenceUpdates.length, 0);
  release();
  app.emit('result', { results: [{ transcript: 'Hey Sora stop listening' }], isFinal: true });
  assert.equal(app.speechStops, 0);
  assert.equal(app.preferenceUpdates.length, 0);
  assert.equal(questions.length, 0);
  app.cleanup();
});

test('ordinary speech can interrupt in commands-only mode without submitting a question', async () => {
  const app = mount({ questionsEnabled: false }), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  await flush(); app.tick();
  const release = app.gate.playback('I will only respond to Hey Sora commands.');
  app.emit('result', { results: [{ transcript: 'Hello how are you' }], isFinal: false });
  await flush(); assert.equal(app.speechStops, 1);
  release();
  app.emit('result', { results: [{ transcript: 'Hello how are you' }], isFinal: true });
  await flush(); assert.equal(questions.length, 0);
  app.cleanup();
});


test('an interrupted speaker prefix is removed from the final command even after its echo tail expires', async t => {
  const app = mount(), controls = [], questions = [];
  app.view.props.value.registerStream(async command => { controls.push(command); return 'Stream paused.'; });
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  await flush(); app.tick();
  const release = app.gate.playback('There is a blue chair near the table.');
  app.emit('result', { results: [{ transcript: 'a blue chair hey sora pause' }], isFinal: false });
  await flush(); release();
  const later = Date.now() + 2000;
  t.mock.method(Date, 'now', () => later);
  app.emit('result', { results: [{ transcript: 'a blue chair hey sora pause stream' }], isFinal: true });
  await flush();
  assert.deepEqual(controls, ['pause-stream']);
  assert.equal(questions.length, 0);
  app.cleanup();
});


test('a new Hey Sora command keeps its wake words when the answer also mentions Hey Sora', () => {
  const gate = new VoiceAudioGate();
  const release = gate.playback('I will only respond to Hey Sora commands.');
  assert.equal(gate.userTranscript('Hey Sora pause stream'), 'Hey Sora pause stream');
  release();
});


test('native voice levels feed the waveform and reset on silence, end and cleanup', async () => {
  const app = mount(); await flush(); app.tick();
  assert.equal(app.starts[0].volumeChangeEventOptions.enabled, true);
  assert.equal(app.starts[0].volumeChangeEventOptions.intervalMillis, 80);
  app.emit('start');
  app.emit('volumechange', { value: 7 });
  assert.equal(app.meter.getSnapshot().listening, true);
  assert.ok(app.meter.getSnapshot().level > 0.5);
  app.tick(); assert.equal(app.meter.getSnapshot().level, 0);
  app.emit('volumechange', { value: 9 });
  app.emit('end');
  assert.deepEqual(app.meter.getSnapshot(), { listening: false, level: 0 });
  app.emit('start'); app.emit('volumechange', { value: 8 });
  app.cleanup(); assert.deepEqual(app.meter.getSnapshot(), { listening: false, level: 0 });
});

test('background microphone events cannot animate the voice waveform', async () => {
  const app = mount(); await flush(); app.tick();
  app.emit('start'); app.appState.currentState = 'background';
  app.emit('volumechange', { value: 10 });
  assert.equal(app.meter.getSnapshot().level, 0);
  app.cleanup();
});


test('mute and unmute require a complete Hey Sora command', () => {
  for (const text of ['Hey Sora mute', 'Hey Sora, mute your voice please']) assert.equal(voiceCommand(text), 'mute');
  assert.equal(voiceCommand('Hey Sora unmute'), 'unmute');
  for (const text of ['mute', 'unmute', 'hey sora do not mute', 'hey sora mute tomorrow']) assert.equal(voiceCommand(text), null);
});

test('muting persists the voice preference while recognition and questions stay active', async () => {
  const app = mount(), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'A chair.', language: 'en' }; });
  await flush(); app.tick();
  const say = async transcript => { app.emit('result', { results: [{ transcript }], isFinal: true }); await flush(); };
  await say('Hey Sora mute');
  assert.equal(app.preferences.speak, false);
  assert.equal(app.preferences.handsFreeQuestions, true);
  assert.ok(app.speechStops > 0);
  await say('What is in front of me');
  assert.deepEqual(questions, ['What is in front of me']);
  assert.equal(app.spoken.length, 0);
  await say('Hey Sora unmute');
  assert.equal(app.preferences.speak, true);
  assert.equal(app.spoken.at(-1), 'Voice unmuted.');
  await say('Describe the scene');
  assert.equal(app.spoken.at(-1), 'A chair.');
  app.cleanup();
});

test('SOS sharing accepts only an explicit location-to-contact instruction', () => {
  for (const text of ['Send my location to my SOS contact', 'Hey Sora, share my location with my emergency contact', 'send location to s o s contact please', 'SOS', 'send SOS', 'send SOS contact', 'Hey Sora SOS', 'S.O.S.', 'send an SOS to my contact please']) {
    assert.deepEqual(voiceInput(text), { kind: 'command', action: 'send-sos-location' });
  }
  for (const text of ['do not send my location to my SOS contact', 'what happens if I send my location to my SOS contact', 'send my location', 'what is SOS', 'do not send SOS', 'SOS tomorrow']) {
    assert.equal(voiceInput(text)?.kind, 'question');
  }
});

test('SOS voice command works without a camera session and suppresses duplicate recognition', async () => {
  const app = mount({ questionsEnabled: false });
  await flush(); app.tick();
  const event = { results: [{ transcript: 'send my location to my sos contact' }], isFinal: true };
  app.emit('result', event); app.emit('result', event);
  await flush();
  assert.equal(app.sosCalls.length, 1);
  assert.ok(app.spoken.includes('Your location email was submitted to your SOS contact.'));
  assert.equal(app.navigation.length, 0);
  app.cleanup();
});

test('route playback phrases are local commands with or without the wake word', () => {
  for (const [action, phrases] of [
    ['next-step', ['next step', 'Hey Sora next step please', 'Étape suivante', 'الخطوة التالية']],
    ['previous-step', ['previous step', 'Hey Sora previous step', 'Étape précédente', 'الخطوة السابقة']],
    ['show-full-route', ['show full route', 'show the full route please', 'Hey Sora show full route', 'Affiche l’itinéraire complet', 'اعرض المسار كاملاً']],
  ]) {
    for (const phrase of phrases) {
      assert.equal(voiceCommand(phrase), action, phrase);
      assert.deepEqual(voiceInput(phrase), { kind: 'command', action });
    }
  }
  for (const phrase of ['What is the next step to the cafe?', 'show full route to the library', 'do not go to the previous step']) {
    assert.equal(voiceInput(phrase).kind, 'question');
  }
});


test('live camera announces fresh obstacle alerts and ignores stale or non-alert results', async () => {
  const alert = { type: 'alert', id: 'obstacle', message: 'A chair blocks the passage.', language: 'en', expires_at: new Date(Date.now() + 5000).toISOString() };
  const fresh = await voiceStartCamera(true, { active: true, event: alert });
  assert.equal(fresh.alerts.length, 1);
  assert.equal(fresh.alerts[0][1], alert.message);
  for (const event of [{ ...alert, expires_at: new Date(Date.now() - 1000).toISOString() }, { ...alert, type: 'observation' }]) {
    const ignored = await voiceStartCamera(true, { active: true, event });
    assert.equal(ignored.alerts.length, 0);
  }
});


test('remembered target notifications preserve their custom speech flag', async () => {
  const event = { type: 'alert', id: 'watch-stop', label: 'remembered_detection', message: 'Detected: a stop sign.', language: 'en', expires_at: new Date(Date.now() + 5000).toISOString() };
  const app = await voiceStartCamera(true, { active: true, event });
  assert.equal(app.alerts.length, 1);
  assert.equal(app.alerts[0][4], true);
});


test('camera detection toggle persists both on and off to the backend session', async () => {
  for (const enabled of [false, true]) {
    const app = await voiceStartCamera(true, { active: true, detectionEnabled: !enabled, toggleDetection: enabled });
    const patch = app.requests.find(request => request[1] === 'PATCH');
    assert.equal(patch[0], '/sessions/voice-session');
    assert.equal(patch[2].alerts_enabled, enabled);
    assert.ok(app.sessionUpdates.some(session => session?.alerts_enabled === enabled));
  }
});

test('failed detection updates leave the session state unchanged and show the error', async () => {
  const app = await voiceStartCamera(true, { active: true, detectionEnabled: true, toggleDetection: false, detectionError: new Error('Detection update failed') });
  assert.equal(app.sessionUpdates.length, 0);
  assert.ok(app.updates.includes('Detection update failed'));
});

test('detection off ignores late automatic alerts on mobile', async () => {
  const event = { type: 'alert', id: 'late-watch', label: 'remembered_detection', message: 'Detected: a laptop.', language: 'en', expires_at: new Date(Date.now() + 5000).toISOString() };
  const app = await voiceStartCamera(true, { active: true, detectionEnabled: false, event });
  assert.equal(app.alerts.length, 0);
});

const spokenRouteIntro = 'Burger King - Baabda is approximately 8.8 km away on foot. Walking directions from Google Maps: 1. Head south on Bmekkine (127 m).';

test('route distance and instruction echoes match spoken numbers and expanded metric units', () => {
  const gate = new VoiceAudioGate();
  gate.playback(spokenRouteIntro);
  for (const text of [
    'Burger King Baabda is approximately eight point eight kilometers away on foot',
    'approximately eight point eight kilometres',
    'eight point eight kilometers away',
    'Burger King Baabda is approximately eight point',
    'Burger King Baabda is approximately eight',
    'one head south on Bmekkine one hundred and twenty seven meters',
    'Head south on Bmekkine 127 metres',
  ]) assert.equal(gate.userTranscript(text), '', text);
  assert.equal(gate.userTranscript('What is the next turn?'), 'What is the next turn?');
  assert.equal(gate.userTranscript('next step'), 'next step');
  assert.equal(gate.userTranscript('show full route'), 'show full route');
  assert.equal(gate.userTranscript('Is Burger King eight kilometers away?'), 'Is Burger King eight kilometers away?');
  assert.equal(gate.userTranscript('eight point eight kilometers away next step'), 'next step');
});

test('distance echoes cannot cut route playback off after the destination summary', async () => {
  const app = mount(), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: 'Unused', language: 'en' }; });
  await flush(); app.tick();
  const release = app.gate.playback(spokenRouteIntro);
  for (const isFinal of [false, true]) {
    app.emit('result', { results: [{ transcript: 'Burger King Baabda is approximately eight point eight kilometers away on foot' }], isFinal });
  }
  await flush();
  assert.equal(app.speechStops, 0);
  assert.equal(questions.length, 0);
  release(); app.cleanup();
});


test('wake-prefixed alert requests reach backend memory instead of becoming unsupported app commands', async () => {
  for (const phrase of ['Hey Sora, alert me when you detect a laptop', 'Hey Sora notify me if you see a car', 'يا سورا نبهني عندما ترى سيارة', 'Hé Sora préviens-moi quand tu vois un panneau stop']) {
    assert.deepEqual(voiceInput(phrase), { kind: 'question', question: phrase });
  }
  assert.deepEqual(voiceInput('Hey Sora, do something unknown'), { kind: 'command', action: null });
  const app = mount(), questions = [];
  app.view.props.value.registerQuestions(async question => { questions.push(question); return { answer: "I'll alert you once when I detect a laptop.", language: 'en' }; });
  await flush(); app.tick();
  app.emit('result', { results: [{ transcript: 'Hey Sora alert me when you detect a laptop' }], isFinal: true });
  await flush();
  assert.deepEqual(questions, ['Hey Sora alert me when you detect a laptop']);
  assert.ok(app.spoken.some(answer => answer.includes("I'll alert you once")));
  app.cleanup();
});

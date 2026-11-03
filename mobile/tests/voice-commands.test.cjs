const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { voiceCommand, voiceInput, VoiceAudioGate } = require('../src/lib/voice-commands.ts');

test('only a wake-prefixed start-stream command controls the app', () => {
  for (const phrase of ['Hey Sora, start stream!', 'HEY SORA START THE STREAM', 'hey sora start stream please']) assert.equal(voiceCommand(phrase), 'start-stream');
  for (const phrase of ['start stream', 'hey sora', 'hello hey sora start stream', 'hey sora do not start stream', 'hey sora start streaming', 'hey sora start stream tomorrow', 'hey sora start stream 123']) assert.equal(voiceCommand(phrase), null);
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
function mount({ native = true, granted = true, permissionPromise, enabled = true, questionsEnabled = true } = {}) {
  const effects = [], cleanups = [], listeners = new Map(), navigation = [], starts = [], spoken = [], statuses = [], timers = new Map();
  const preferences = { onboarded: true, voiceCommands: enabled, handsFreeQuestions: questionsEnabled };
  const preferenceUpdates = [];
  const gate = new VoiceAudioGate();
  const appState = { currentState: 'active', addEventListener: () => ({ remove() {} }) };
  let imports = 0, aborts = 0, stops = 0, now = 10000;
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
      if (name === '@/lib/voice-commands') return { voiceAudioGate: gate, voiceInput };
      if (name === '@/lib/speech') return { speech: { async answer(text) { spoken.push(text); } } };
      if (name === 'expo-speech-recognition') { imports++; assert.equal(native, true); return { ExpoSpeechRecognitionModule: recognizer }; }
      throw new Error(`Unexpected import ${name}`);
    },
  });
  const view = exports.VoiceCommandsProvider({ children: null });
  effects.forEach(fn => { const cleanup = fn(); if (cleanup) cleanups.push(cleanup); });
  return {
    navigation, starts, spoken, statuses, gate, appState, view, imports, preferenceUpdates, preferences,
    get stops() { return stops; },
    get aborts() { return aborts; },
    emit: (name, event) => listeners.get(name)?.(event),
    tick() { const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn()); now += 1000; },
    cleanup() { cleanups.forEach(fn => fn()); },
  };
}
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

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

test('old native builds and disabled voice commands leave the app usable', async () => {
  const old = mount({ native: false });
  assert.equal(old.imports, 0);
  assert.match(old.view.props.value.status, /new development build/);
  old.cleanup();
  const disabled = mount({ enabled: false });
  await flush(); disabled.tick(); assert.equal(disabled.starts.length, 0);
  disabled.cleanup();
});


const cameraSource = ts.transpileModule(fs.readFileSync(require.resolve('../src/app/camera.tsx'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
async function voiceStartCamera(granted, { active = false, paused = false, question, command, closeError } = {}) {
  const effects = [], requests = [], spoken = [], updates = [];
  const session = { id: 'voice-session', status: 'active', language: 'en' };
  const reply = { answer: 'A chair beside a table.', language: 'en' };
  let voiceQuestion, voiceControl, stateIndex = 0;
  const exports = {};
  const jsx = (type, props) => ({ type, props });
  vm.runInNewContext(cameraSource + '\nexports.captureForTest = Capture;', {
    exports, setTimeout, clearTimeout,
    require(name) {
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === 'react') return {
        useState: initial => { const index = stateIndex++; return [active && index === 0 ? session : active && index === 6 ? true : index === 10 ? paused : initial, value => updates.push(value)]; }, useRef: current => ({ current }),
        useCallback: fn => fn, useEffect: fn => effects.push(fn),
      };
      if (name === 'react-native') return { AppState: { currentState: 'active', addEventListener: () => ({ remove() {} }) }, StyleSheet: { create: value => value }, Platform: { OS: 'ios' } };
      if (name === 'expo-camera') return { useCameraPermissions: () => [null, async () => ({ granted })] };
      if (name === 'expo-router') return { useFocusEffect() {}, useLocalSearchParams: () => ({ mode: 'live', voiceStart: '123' }) };
      if (name === '@/providers/voice-commands') return { useHandsFreeQuestions(handler) { voiceQuestion = handler; }, useVoiceStreamControls(handler) { voiceControl = handler; }, useVoiceCommands: () => ({ status: '' }) };
      if (name === '@/providers/auth') return { useAuth: () => ({ api: { async request(...args) { requests.push(args); if (args[0].endsWith('/close') && closeError) throw closeError; return args[0].endsWith('/questions') ? reply : session; } } }) };
      if (name === '@/providers/preferences') return { usePreferences: () => ({ colors: {}, preferences: { guidance: false } }) };
      if (name === '@/lib/speech') return { speech: { async answer(text) { spoken.push(text); }, async stop() {} } };
      return {};
    },
  });
  exports.captureForTest();
  const cleanups = effects.map(fn => fn());
  await flush(); await flush();
  // React effects may run again: one voice request must create only one session.
  effects.forEach(fn => fn());
  await flush();
  const askedReply = question ? await voiceQuestion(question) : null;
  let controlReply, controlError;
  try { if (command) controlReply = await voiceControl(command); } catch (error) { controlError = error; }
  cleanups.forEach(fn => { if (typeof fn === 'function') fn(); });
  return { requests, spoken, updates, session, askedReply, controlReply, controlError };
}

test('a voice start requests camera permission and creates exactly one streaming session without taps', async () => {
  const app = await voiceStartCamera(true);
  assert.equal(app.requests.length, 1);
  assert.equal(app.requests[0][0], '/sessions');
  assert.equal(app.requests[0][1], 'POST');
  assert.equal(app.requests[0][2].consent, true);
  assert.ok(app.updates.includes(app.session));
  assert.ok(app.spoken.includes('Starting your stream.'));
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
  assert.ok(app.updates.includes(null));
  assert.match(app.controlReply, /Stream stopped/);
});

test('failed session closure keeps the camera paused and propagates the error for spoken feedback', async () => {
  const failure = new Error('Server unavailable.');
  const app = await voiceStartCamera(true, { active: true, command: 'stop-stream', closeError: failure });
  assert.equal(app.controlError, failure);
  assert.equal(app.updates.includes(null), false);
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

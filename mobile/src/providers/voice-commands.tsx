import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AccessibilityInfo, AppState, Platform } from 'react-native';
import { requireOptionalNativeModule } from 'expo';
import { router, useFocusEffect } from 'expo-router';
import type { ExpoSpeechRecognitionModule } from 'expo-speech-recognition';
import { voiceAudioGate, voiceInput, type StreamCommand } from '@/lib/voice-commands';
import { shareSOSLocation } from '@/lib/emergency';
import { voiceLevel } from '@/lib/voice-level';
import { speech } from '@/lib/speech';
import type { Answer } from '@/lib/api';
import { useAuth } from './auth';
import { usePreferences } from './preferences';

type QuestionHandler = (question: string) => Promise<Pick<Answer, 'answer' | 'language'>>;
type QuestionTarget = { ask: QuestionHandler; contextKey?: string };
type StreamHandler = (command: StreamCommand) => Promise<string>;
type StreamTarget = { control: StreamHandler; isPaused: () => boolean };
const Context = createContext<{ status: string; retry: () => void; setQuestionListening: (enabled: boolean) => void; registerStream: (control: StreamHandler, isPaused?: () => boolean) => () => void; refreshStreamState: () => void; registerQuestions: (ask: QuestionHandler, contextKey?: string) => () => void }>({ status: '', retry: () => {}, setQuestionListening: () => {}, registerStream: () => () => {}, refreshStreamState: () => {}, registerQuestions: () => () => {} });
export function VoiceCommandsProvider({ children }: { children: ReactNode }) {
  const { api, tokens, ready } = useAuth();
  const { preferences, update } = usePreferences();
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const [paused, setPaused] = useState(voiceAudioGate.paused);
  const [status, setStatus] = useState('Preparing voice listening…');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { void speech.setMuted(!preferences.speak).catch(() => {}); }, [preferences.speak]);
  const lastInput = useRef({ text: '', time: 0 });
  const questionTarget = useRef<QuestionTarget | null>(null);
  const asking = useRef(false);
  const sendingSOS = useRef(false);
  const questionGeneration = useRef(0);
  const questionsEnabled = useRef(preferences.handsFreeQuestions);
  const streamPaused = useRef(false);
  const [commandsOnlyForStream, setCommandsOnlyForStream] = useState(false);
  const [thinking, setThinking] = useState(false);
  const cancelQuestions = useCallback(() => {
    questionGeneration.current++;
    asking.current = false;
    setThinking(false);
  }, []);
  useEffect(() => {
    if (questionsEnabled.current !== preferences.handsFreeQuestions) {
      questionGeneration.current++;
      asking.current = false;
    }
    questionsEnabled.current = preferences.handsFreeQuestions;
  }, [preferences.handsFreeQuestions]);
  const setQuestionListening = useCallback((enabled: boolean) => {
    questionsEnabled.current = enabled;
    cancelQuestions();
    update({ handsFreeQuestions: enabled });
  }, [cancelQuestions, update]);
  const registerQuestions = useCallback((ask: QuestionHandler, contextKey?: string) => {
    const target = { ask, contextKey };
    questionTarget.current = target;
    return () => { if (questionTarget.current === target) questionTarget.current = null; };
  }, []);
  const streamTarget = useRef<StreamTarget | null>(null);
  const streamTargets = useRef<StreamTarget[]>([]);
  const controllingStream = useRef(false);
  const refreshStreamState = useCallback(() => {
    const next = streamTarget.current?.isPaused() ?? false;
    if (streamPaused.current !== next) cancelQuestions();
    streamPaused.current = next;
    setCommandsOnlyForStream(next);
  }, [cancelQuestions]);
  const registerStream = useCallback((control: StreamHandler, isPaused: () => boolean = () => false) => {
    const target = { control, isPaused };
    streamTargets.current.push(target);
    streamTarget.current = target;
    refreshStreamState();
    return () => {
      streamTargets.current = streamTargets.current.filter(value => value !== target);
      streamTarget.current = streamTargets.current.at(-1) || null;
      refreshStreamState();
    };
  }, [refreshStreamState]);
  const blocked = useRef(false);
  const [recognizer] = useState<typeof ExpoSpeechRecognitionModule | null>(() => {
    // An older development build must still open without the new native module.
    if (Platform.OS === 'web' || !requireOptionalNativeModule('ExpoSpeechRecognition')) return null;
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('expo-speech-recognition').ExpoSpeechRecognitionModule;
  });
  useEffect(() => {
    const sub = AppState.addEventListener('change', state => setForeground(state === 'active'));
    return () => sub.remove();
  }, []);
  useEffect(() => voiceAudioGate.subscribe(() => {
    if (voiceAudioGate.paused) recognizer?.abort();
    setPaused(voiceAudioGate.paused);
  }), [recognizer]);
  useEffect(() => {
    if (!ready || !tokens || !preferences.onboarded || !preferences.voiceCommands) return;
    if (!recognizer) return;
    if (!foreground || paused || blocked.current) return;
    let disposed = false;
    voiceAudioGate.setRecognitionState('starting');
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let interrupting = false;
    let utterancePlayback: string[] = [];
    let utteranceTimer: ReturnType<typeof setTimeout> | undefined;
    let levelTimer: ReturnType<typeof setTimeout> | undefined;
    const listeningStatus = 'Listening. Ask a question, or say “Hey Sora” for an app command.';
    function stillHere(target: QuestionTarget) {
      return questionTarget.current === target && questionsEnabled.current && !streamPaused.current && AppState.currentState === 'active';
    }
    async function askQuestion(question: string) {
      if (asking.current || !questionsEnabled.current || streamPaused.current) return;
      const target = questionTarget.current;
      if (!target) {
        void speech.answer('Start a stream first by saying Hey Sora, start stream. Then ask about your surroundings.', 'en');
        return;
      }
      const generation = questionGeneration.current;
      asking.current = true; setThinking(true);
      try {
        const reply = await target.ask(question);
        if (generation === questionGeneration.current && stillHere(target)) await speech.answer(reply.answer, reply.language);
      } catch (error) {
        if (generation === questionGeneration.current && stillHere(target)) await speech.answer(error instanceof Error ? error.message : 'Unable to answer. Please try again.', 'en');
      } finally { if (generation === questionGeneration.current) { asking.current = false; setThinking(false); } }
    }
    async function controlStream(command: StreamCommand) {
      if (controllingStream.current) return;
      const target = streamTarget.current;
      if (!target) {
        void speech.answer('There is no stream open to control. Say Hey Sora, start stream first.', 'en');
        return;
      }
      controllingStream.current = true;
      if (command !== 'resume-stream') {
        streamPaused.current = true; setCommandsOnlyForStream(true); cancelQuestions();
      }
      try {
        const message = await target.control(command);
        if (command === 'resume-stream') { streamPaused.current = false; setCommandsOnlyForStream(false); }
        if (AppState.currentState === 'active') await speech.answer(message, 'en');
      } catch (error) {
        refreshStreamState();
        if (AppState.currentState === 'active') await speech.answer(error instanceof Error ? error.message : 'Unable to control your stream. Please try again.', 'en');
      } finally { controllingStream.current = false; }
    }
    function fail(message: string) {
      blocked.current = true;
      clearTimeout(levelTimer); voiceLevel.setListening(false);
      voiceAudioGate.setRecognitionState('off');
      setStatus(message);
      AccessibilityInfo.announceForAccessibility(message);
    }
    function start() {
      if (disposed || AppState.currentState !== 'active' || voiceAudioGate.paused || blocked.current) return;
      try {
        recognizer!.start({ lang: 'en-US', continuous: true, interimResults: true, maxAlternatives: 1, volumeChangeEventOptions: { enabled: true, intervalMillis: 80 }, iosVoiceProcessingEnabled: true, iosCategory: { category: 'playAndRecord', categoryOptions: ['defaultToSpeaker', 'allowBluetooth'], mode: 'voiceChat' }, contextualStrings: ['Hey Sora', 'Hey Sora start stream', 'Hey Sora pause stream', 'Hey Sora resume stream', 'Hey Sora stop stream', 'Hey Sora stop listening', 'Hey Sora start listening', 'Hey Sora resume listening', 'Hey Sora mute', 'Hey Sora unmute', 'Describe the scene'], recordingOptions: { persist: false } });
      } catch { fail('Voice listening could not start. Retry voice commands in Preferences.'); }
    }
    const subscriptions = [
      recognizer.addListener('start', () => { voiceLevel.setListening(true); voiceAudioGate.setRecognitionState('ready'); utterancePlayback = []; if (!disposed) setStatus(listeningStatus); }),
      recognizer.addListener('volumechange', event => {
        if (disposed || AppState.currentState !== 'active' || voiceAudioGate.paused || blocked.current) return;
        voiceLevel.update(event.value);
        clearTimeout(levelTimer);
        levelTimer = setTimeout(() => voiceLevel.update(0), 300);
      }),
      recognizer.addListener('result', event => {
        if (disposed || AppState.currentState !== 'active' || voiceAudioGate.paused || blocked.current) return;
        failures = 0;
        clearTimeout(utteranceTimer);
        if (!utterancePlayback.length) utterancePlayback = voiceAudioGate.playbackTexts;
        const transcript = voiceAudioGate.userTranscript(event.results[0]?.transcript || '', utterancePlayback);
        if (event.isFinal) utterancePlayback = [];
        if (!transcript) return;
        if (voiceAudioGate.playing && !interrupting) {
          // Interrupt on the first user partial result; do not wait for a final question.
          // Keep recognition running so the rest of that utterance is still captured.
          interrupting = true;
          void speech.stop().catch(() => {}).finally(() => { interrupting = false; });
        }
        if (!event.isFinal) {
          // iOS continuous recognition may only finalize when explicitly stopped.
          // Wait for a pause, then request the final transcript before acting.
          utteranceTimer = setTimeout(() => {
            if (!disposed && !voiceAudioGate.paused) recognizer.stop();
          }, 1200);
          return;
        }
        const input = voiceInput(transcript);
        if (!input) return;
        const key = transcript.toLocaleLowerCase().replace(/\s+/g, ' ');
        if (lastInput.current.text === key && Date.now() - lastInput.current.time < 2000) return;
        lastInput.current = { text: key, time: Date.now() };
        // Reset cumulative transcripts before listening for the next utterance.
        recognizer.abort();
        if (input.kind === 'command') {
          if (input.action === 'send-sos-location') {
            if (sendingSOS.current) return;
            sendingSOS.current = true;
            setStatus('Getting your location for SOS…');
            void shareSOSLocation(api).then(message => {
              setStatus(message); return speech.answer(message, 'en');
            }).catch(error => {
              const message = error instanceof Error ? error.message : 'Unable to send your SOS location.';
              setStatus(message); return speech.answer(message, 'en');
            }).finally(() => { sendingSOS.current = false; });
          } else if (input.action === 'mute' || input.action === 'unmute') {
            const muted = input.action === 'mute';
            // Apply immediately, including an answer already waiting to speak.
            void speech.setMuted(muted).catch(() => {});
            update({ speak: !muted });
            setStatus(muted ? 'Sora voice muted. Say Hey Sora, unmute to restore it.' : listeningStatus);
            if (!muted) void speech.answer('Voice unmuted.', 'en');
          } else if (input.action === 'stop-listening' || input.action === 'start-listening') {
            const enabled = input.action === 'start-listening';
            setQuestionListening(enabled);
            void speech.answer(enabled
              ? streamPaused.current ? 'Question listening is on. Resume your stream to ask questions.' : 'Listening for questions again.'
              : 'I will only respond to Hey Sora commands. Say Hey Sora, start listening to ask questions again.', 'en');
          } else if (input.action === 'start-stream') router.navigate({ pathname: '/camera', params: { mode: 'live', voiceStart: String(Date.now()) } });
          else if (input.action) void controlStream(input.action);
          else void speech.answer('That app command is not available yet.', 'en');
        } else void askQuestion(input.question);
      }),
      recognizer.addListener('error', event => {
        clearTimeout(levelTimer); voiceLevel.setListening(false);
        utterancePlayback = [];
        clearTimeout(utteranceTimer);
        if (disposed || event.error === 'aborted' || event.error === 'no-speech') return;
        failures++;
        if (['not-allowed', 'service-not-allowed', 'language-not-supported', 'audio-capture'].includes(event.error) || failures >= 3) {
          fail('Voice listening is unavailable. Check microphone and speech permissions, then retry in Preferences.');
        }
      }),
      recognizer.addListener('end', () => {
        clearTimeout(levelTimer); voiceLevel.setListening(false);
        voiceAudioGate.setRecognitionState(disposed || blocked.current ? 'off' : 'starting');
        utterancePlayback = [];
        clearTimeout(utteranceTimer);
        if (!disposed && !blocked.current) { clearTimeout(timer); timer = setTimeout(start, Math.min(500 * 2 ** failures, 5000)); }
      }),
    ];
    void (async () => {
      try {
        if (!recognizer.isRecognitionAvailable()) { fail('Speech recognition is unavailable on this phone.'); return; }
        const permission = await recognizer.requestPermissionsAsync();
        if (disposed) return;
        if (!permission.granted) { fail('Allow microphone and speech recognition access in device settings to use Hey Sora.'); return; }
        // Leave a short gap after SORA speaks so its audio cannot trigger a command.
        timer = setTimeout(start, 350);
      } catch { if (!disposed) fail('Unable to enable voice listening. Retry in Preferences.'); }
    })();
    return () => { disposed = true; clearTimeout(levelTimer); voiceLevel.setListening(false); voiceAudioGate.setRecognitionState('off'); clearTimeout(timer); clearTimeout(utteranceTimer); subscriptions.forEach(sub => sub.remove()); recognizer.abort(); };
  }, [api, ready, tokens, preferences.onboarded, preferences.voiceCommands, recognizer, foreground, paused, attempt, cancelQuestions, refreshStreamState, setQuestionListening, update]);
  const displayStatus = !ready || !tokens || !preferences.onboarded || !preferences.voiceCommands ? 'Voice commands are off.' : !recognizer ? Platform.OS === 'web' ? 'Voice commands are available in the mobile app.' : 'Install a new development build to enable Hey Sora voice commands.' : !foreground ? 'Voice listening pauses while SORA is in the background.' : paused ? 'Voice listening paused for audio.' : commandsOnlyForStream ? 'Stream paused. Only Hey Sora commands are active.' : !preferences.handsFreeQuestions ? 'Only Hey Sora commands are active. Say “Hey Sora, start listening” for questions.' : thinking ? 'Thinking about your question…' : status;
  return <Context.Provider value={{ status: displayStatus, registerQuestions, registerStream, refreshStreamState, setQuestionListening, retry: () => { blocked.current = false; setAttempt(value => value + 1); } }}>{children}</Context.Provider>;
}
export function useVoiceCommands() { return useContext(Context); }

// The focused screen owns the question context; background screens cannot receive it.
export function useHandsFreeQuestions(handler: QuestionHandler, contextKey?: string) {
  const { registerQuestions } = useVoiceCommands();
  const latest = useRef(handler);
  useEffect(() => { latest.current = handler; }, [handler]);
  useFocusEffect(useCallback(() => registerQuestions(question => latest.current(question), contextKey), [registerQuestions, contextKey]));
}

export function useVoiceStreamControls(handler: StreamHandler, available: boolean, paused = false) {
  const { registerStream, refreshStreamState } = useVoiceCommands();
  const latest = useRef({ handler, paused });
  useEffect(() => { latest.current = { handler, paused }; refreshStreamState(); }, [handler, paused, refreshStreamState]);
  // Keep a session controllable from Settings and other screens until it closes.
  useEffect(() => {
    if (available) return registerStream(command => latest.current.handler(command), () => latest.current.paused);
  }, [registerStream, available]);
}

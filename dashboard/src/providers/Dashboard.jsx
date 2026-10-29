import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useAuth } from './Auth.jsx';
import { chooseSession, subscribeEvents } from '../lib/live.js';
const DashboardContext = createContext(null);
export function DashboardProvider({ children }) {
  const { api, tokens } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [followLive, setFollowLive] = useState(true);
  const [metrics, setMetrics] = useState(null);
  const [frames, setFrames] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState(null);
  const [connection, setConnection] = useState('Connecting');
  const [error, setError] = useState('');
  const [networkError, setNetworkError] = useState('');
  const [loading, setLoading] = useState(true);
  const [frameMore, setFrameMore] = useState(false);
  const [questionMore, setQuestionMore] = useState(false);
  const [spoken, setSpoken] = useState(false);
  const [mediaError, setMediaError] = useState('');
  const current = useRef('');
  const loaded = useRef({ frames: 50, questions: 50 });
  const spokenRef = useRef(spoken);
  useEffect(() => { spokenRef.current = spoken; }, [spoken]);
  const audio = useRef(null);
  const mediaUrl = useRef(null);
  const speechGeneration = useRef(0);
  const session = sessions.find(item => item.id === selectedId) || null;
  const stopSpeaking = useCallback(() => {
    speechGeneration.current++;
    audio.current?.pause(); audio.current = null;
    if (mediaUrl.current) URL.revokeObjectURL(mediaUrl.current);
    mediaUrl.current = null;
  }, []);
  const play = useCallback(async (path, body) => {
    stopSpeaking(); setMediaError('');
    const generation = speechGeneration.current;
    const response = await api.response(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
    const blob = await response.blob();
    if (generation !== speechGeneration.current) return;
    const url = URL.createObjectURL(blob); mediaUrl.current = url;
    const player = new Audio(url); audio.current = player;
    player.onerror = () => setMediaError('Unable to play this audio.');
    player.onended = () => { if (audio.current === player) stopSpeaking(); };
    try { await player.play(); } catch { stopSpeaking(); throw new Error('Playback was blocked. Use the answer’s Play button to hear it.'); }
  }, [api, stopSpeaking]);
  useEffect(() => () => stopSpeaking(), [stopSpeaking]);
  useEffect(() => {
    const hide = () => { if (document.hidden) stopSpeaking(); };
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, [stopSpeaking]);
  const refreshSessions = useCallback(async signal => {
    const [summary, ownSessions, values] = await Promise.all([
      api.request('/dashboard?own_only=true&limit=200', 'GET', undefined, signal), api.request('/sessions?own_only=true&limit=200', 'GET', undefined, signal), api.request('/metrics?own_only=true', 'GET', undefined, signal),
    ]);
    if (signal?.aborted) return;
    const byId = new Map(summary.sessions.map(item => [item.session_id, item]));
    const rows = ownSessions.filter(item => item.owner_id === tokens.user.id).map(item => ({ ...item, ...byId.get(item.id) }));
    setSessions(rows); setMetrics(values);
    setSelectedId(previous => chooseSession(rows, previous, followLive));
  }, [api, tokens.user.id, followLive]);
  useEffect(() => {
    let disposed = false;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try { await refreshSessions(controller.signal); if (!disposed) setNetworkError(''); }
      catch (e) { if (!disposed) setNetworkError(e.message); }
      finally { if (!disposed) { setLoading(false); timer = setTimeout(() => void poll(), 4000); } }
    }
    void poll();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, [refreshSessions]);
  const refreshData = useCallback(async (id = selectedId) => {
    if (!id) return;
    const path = `/sessions/${id}`;
    async function readLoaded(kind) {
      const count = Math.max(50, loaded.current[kind]);
      const pages = [];
      for (let offset = 0; offset < count; offset += 200) pages.push(api.request(`${path}/${kind}?limit=${Math.min(200, count - offset)}&offset=${offset}`));
      return (await Promise.all(pages)).flat();
    }
    const [images, answers, warnings, live] = await Promise.all([
      readLoaded('frames'), readLoaded('questions'), api.request(`${path}/alerts?limit=50`), api.request(`${path}/stream/status`),
    ]);
    if (current.current !== id) return;
    setFrames(images); setQuestions(answers); setAlerts(warnings); setStatus(live);
    setFrameMore(images.length >= loaded.current.frames); setQuestionMore(answers.length >= loaded.current.questions);
  }, [api, selectedId]);
  useEffect(() => {
    current.current = selectedId;
    loaded.current = { frames: 50, questions: 50 };
    stopSpeaking(); setFrames([]); setQuestions([]); setAlerts([]); setEvents([]); setStatus(null);
    if (!selectedId) return;
    let disposed = false;
    let timer;
    let refreshTimer;
    const refresh = () => { void refreshData(selectedId).catch(e => { if (!disposed) setError(e.message); }); };
    const unsubscribe = subscribeEvents(api, selectedId, event => {
      if (event.type === 'ready') refresh();
      if (event.type === 'session_updated' && event.session) setSessions(previous => previous.map(item => item.id === event.session.id ? { ...item, ...event.session } : item));
      if (!['heartbeat', 'ready'].includes(event.type)) setEvents(previous => [{ ...event, receivedAt: new Date().toISOString() }, ...previous].slice(0, 30));
      if (event.frame) setFrames(previous => [event.frame, ...previous.filter(item => item.id !== event.frame.id)].slice(0, Math.max(50, previous.length)));
      if (event.question) {
        setQuestions(previous => [event.question, ...previous.filter(item => item.id !== event.question.id)]);
        if (spokenRef.current) void play(`/sessions/${selectedId}/questions/${event.question.id}/audio`).catch(e => setMediaError(e.message));
      }
      if (event.type === 'alert') {
        setAlerts(previous => [{ ...event, created_at: new Date().toISOString() }, ...previous].slice(0, 50));
        if (spokenRef.current && event.message) void play('/speech/synthesis', { text: event.message, language: event.language || 'en' }).catch(e => setMediaError(e.message));
      }
      if (event.type === 'processing_error') setError(event.message || event.code || 'Frame processing failed.');
      if (event.type.startsWith('stream_')) {
        clearTimeout(refreshTimer); refreshTimer = setTimeout(refresh, 100);
      }
    }, setConnection);
    async function poll() { refresh(); if (!disposed) timer = setTimeout(() => void poll(), 10000); }
    void poll();
    return () => { disposed = true; current.current = ''; unsubscribe(); clearTimeout(timer); clearTimeout(refreshTimer); stopSpeaking(); };
  }, [api, selectedId, refreshData, play, stopSpeaking]);
  async function loadMore(kind) {
    const id = selectedId;
    const previous = kind === 'frames' ? frames : questions;
    const result = await api.request(`/sessions/${id}/${kind}?limit=50&offset=${previous.length}`);
    if (current.current !== id) return;
    const update = kind === 'frames' ? setFrames : setQuestions;
    loaded.current[kind] = previous.length + result.length;
    update(items => [...new Map([...items, ...result].map(item => [item.id, item])).values()]);
    (kind === 'frames' ? setFrameMore : setQuestionMore)(result.length === 50);
  }
  function select(id) { setFollowLive(false); setSelectedId(id); }
  return <DashboardContext.Provider value={{ api, sessions, session, selectedId, select, followLive, setFollowLive, metrics, frames, questions, alerts, events, status, connection, error: error || networkError, setError, loading, refreshSessions, refreshData, loadMore, frameMore, questionMore, spoken, setSpoken, play, stopSpeaking, mediaError, setMediaError }}>{children}</DashboardContext.Provider>;
}
export function useDashboard() { return useContext(DashboardContext); }

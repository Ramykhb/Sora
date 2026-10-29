import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { ApiClient } from '../lib/api.js';
const AuthContext = createContext(null);
const storageKey = 'sora.dashboard.refresh.v1';
export function AuthProvider({ children }) {
  const [tokens, setTokens] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const bootstrap = useRef(null);
  const [api] = useState(() => new ApiClient(import.meta.env.VITE_API_URL || '', value => {
    if (value) sessionStorage.setItem(storageKey, value.refresh_token);
    else sessionStorage.removeItem(storageKey);
    setTokens(value);
  }));
  useEffect(() => {
    let disposed = false;
    if (!bootstrap.current) bootstrap.current = (async () => {
      const refreshToken = sessionStorage.getItem(storageKey);
      if (refreshToken) await api.restore(refreshToken);
    })();
    bootstrap.current.catch(e => { if (!disposed) setError(e.message); }).finally(() => { if (!disposed) setReady(true); });
    return () => { disposed = true; };
  }, [api, attempt]);
  function retry() { setReady(false); setError(''); bootstrap.current = null; setAttempt(value => value + 1); }
  return <AuthContext.Provider value={{ api, tokens, ready, error, retry }}>{children}</AuthContext.Provider>;
}
export function useAuth() { return useContext(AuthContext); }

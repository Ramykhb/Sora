import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import { ApiClient, type Tokens } from '@/lib/api';

const key = 'sora.refresh.v1';
const host = Constants.expoConfig?.hostUri?.split(':')[0];
export const baseUrl = (process.env.EXPO_PUBLIC_API_URL || `http://${host || (Platform.OS === 'android' ? '10.0.2.2' : 'localhost')}:8000`).replace(/\/+$/, '');
const AuthContext = createContext<{ api: ApiClient; tokens: Tokens | null; ready: boolean; error: string; retry: () => void } | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [tokens, setTokens] = useState<Tokens | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const bootstrap = useRef<Promise<void> | null>(null);
  const [api] = useState(() => new ApiClient(baseUrl, async (value) => {
    if (Platform.OS === 'web') {
      if (value) sessionStorage.setItem(key, value.refresh_token);
      else sessionStorage.removeItem(key);
    } else if (value) await SecureStore.setItemAsync(key, value.refresh_token);
    else await SecureStore.deleteItemAsync(key);
    setTokens(value);
  }));
  useEffect(() => {
    let cancelled = false;
    if (!bootstrap.current) bootstrap.current = (async () => {
      const saved = Platform.OS === 'web' ? sessionStorage.getItem(key) : await SecureStore.getItemAsync(key);
      if (saved) {
        // Only refresh tokens persist; access tokens stay in memory.
        await api.restore(saved);
      }
    })();
    void bootstrap.current.catch(e => {
      if (!cancelled) setError(e instanceof Error ? e.message : 'Unable to restore sign-in.');
    }).finally(() => { if (!cancelled) setReady(true); });
    return () => { cancelled = true; };
  }, [api, attempt]);
  return <AuthContext.Provider value={{ api, tokens, ready, error, retry: () => { setReady(false); setError(''); bootstrap.current = null; setAttempt(v => v + 1); } }}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider is missing');
  return value;
}

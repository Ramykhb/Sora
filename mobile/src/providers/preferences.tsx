import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Platform, useColorScheme } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import * as SplashScreen from 'expo-splash-screen';
import * as SystemUI from 'expo-system-ui';
import { useFonts } from 'expo-font';
import { StatusBar } from 'expo-status-bar';
import { NavigationBar } from 'expo-navigation-bar';

void SplashScreen.preventAutoHideAsync().catch(() => {});
export const palettes = {
  light: {
    background: '#E8F0F9', pageGlow: '#FAFDFF', surface: '#FFFFFF', surfaceBottom: '#F5F9FF',
    elevated: '#DCEBFA', accentSurface: '#D8F0FF', accentSurfaceBottom: '#ECF8FF',
    text: '#0B1838', muted: '#536781', border: '#D3DFEF', separator: '#E5ECF5',
    primary: '#066AFF', primaryBright: '#2996FF', accent: '#00BEEB', danger: '#B32638',
    trackOff: '#C5D1E1', nav: '#FCFEFF', heroArrow: '#F5FCFF', heroArrowInk: '#0875F5',
    heroSheen: '#FFFFFF55', heroEdge: '#FFFFFF75',
    cardShadow: '0 7px 20px rgba(35, 69, 113, 0.10), 0 1px 3px rgba(35, 69, 113, 0.05)',
    quietShadow: '0 3px 10px rgba(35, 69, 113, 0.06)',
    primaryShadow: '0 7px 18px rgba(0, 99, 235, 0.22)',
    navShadow: '0 -5px 20px rgba(35, 69, 113, 0.05)',
    gradient: ['#18CDE5', '#1685FF', '#48D6EF'] as const,
  },
  dark: {
    background: '#060A10', pageGlow: '#101A27', surface: '#26313E', surfaceBottom: '#1C2531',
    elevated: '#324255', accentSurface: '#283E53', accentSurfaceBottom: '#203042',
    text: '#F5F7FA', muted: '#AFBDD0', border: '#394655', separator: '#334050',
    primary: '#0A84FF', primaryBright: '#309CFF', accent: '#29BCFF', danger: '#FF9DA8',
    trackOff: '#4C5B6F', nav: '#141C27', heroArrow: '#FFFFFF2E', heroArrowInk: '#FFFFFF',
    heroSheen: '#FFFFFF16', heroEdge: '#529EFF66',
    cardShadow: '0 8px 20px rgba(0, 0, 0, 0.24), 0 1px 2px rgba(0, 0, 0, 0.14)',
    quietShadow: '0 3px 10px rgba(0, 0, 0, 0.15)',
    primaryShadow: '0 7px 18px rgba(0, 83, 205, 0.24)',
    navShadow: '0 -5px 20px rgba(0, 0, 0, 0.18)',
    gradient: ['#102F56', '#005EDB', '#087FF4'] as const,
  },
};
export type Preferences = { theme: 'system' | 'light' | 'dark'; speak: boolean; guidance: boolean; vibration: boolean; largerText: boolean; highContrast: boolean; onboarded: boolean };
const defaults: Preferences = { theme: 'system', speak: true, guidance: true, vibration: true, largerText: false, highContrast: false, onboarded: false };
const key = 'sora.preferences.v1';
const Context = createContext<{ preferences: Preferences; update: (value: Partial<Preferences>) => void; colors: typeof palettes.light | typeof palettes.dark; dark: boolean; storageError: string } | null>(null);
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [preferences, setPreferences] = useState(defaults);
  const [ready, setReady] = useState(false);
  const [storageError, setStorageError] = useState('');
  const saveQueue = useRef(Promise.resolve());
  const [fonts, fontError] = useFonts({ Sora: require('../../assets/fonts/Sora.ttf') });
  useEffect(() => { let mounted = true; void (async () => {
    try {
      const raw = Platform.OS === 'web' ? localStorage.getItem(key) : await SecureStore.getItemAsync(key);
      if (raw && mounted) {
        const saved = JSON.parse(raw);
        const next = { ...defaults };
        for (const name of Object.keys(defaults) as (keyof Preferences)[]) {
          if (name === 'theme') { if (['system', 'light', 'dark'].includes(saved.theme)) next.theme = saved.theme; }
          else if (typeof saved[name] === 'boolean') next[name] = saved[name];
        }
        setPreferences(next);
      }
    } catch { if (mounted) setStorageError('Preferences could not be restored. Please select them again.'); }
    finally { if (mounted) setReady(true); }
  })(); return () => { mounted = false; }; }, []);
  const dark = (preferences.theme === 'system' ? system : preferences.theme) === 'dark';
  const base = palettes[dark ? 'dark' : 'light'];
  const colors = preferences.highContrast ? { ...base, muted: base.text, border: dark ? '#A7B4C8' : '#4A6386' } : base;
  useEffect(() => { void SystemUI.setBackgroundColorAsync(colors.background).catch(() => {}); }, [colors.background]);
  useEffect(() => { if (ready && (fonts || fontError)) void SplashScreen.hideAsync().catch(() => {}); }, [ready, fonts, fontError]);
  useEffect(() => {
    if (!ready) return;
    const value = JSON.stringify(preferences);
    saveQueue.current = saveQueue.current.then(async () => {
      try { if (Platform.OS === 'web') localStorage.setItem(key, value); else await SecureStore.setItemAsync(key, value); }
      catch { setStorageError('Your changes apply now but could not be saved on this device.'); }
    });
  }, [preferences, ready]);
  if (!ready || (!fonts && !fontError)) return null;
  return <Context.Provider value={{ preferences, update: value => setPreferences(previous => ({ ...previous, ...value })), colors, dark, storageError }}><StatusBar style={dark ? 'light' : 'dark'} /><NavigationBar style={dark ? 'light' : 'dark'} />{children}</Context.Provider>;
}
export function usePreferences() { const value = useContext(Context); if (!value) throw new Error('PreferencesProvider is missing'); return value; }

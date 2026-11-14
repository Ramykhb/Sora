import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Appearance, Platform, useColorScheme } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import * as SplashScreen from 'expo-splash-screen';
import * as SystemUI from 'expo-system-ui';
import { useFonts } from 'expo-font';
import { StatusBar } from 'expo-status-bar';
import { NavigationBar } from 'expo-navigation-bar';
import { voiceLanguage, type VoiceLanguage } from '@/lib/voice-language';

void SplashScreen.preventAutoHideAsync().catch(() => {});
/** Shared dashboard palette. Both appearances keep the same purple identity. */
export const palettes = {
  light: {
    background: '#F5F3FA', pageGlow: '#F0EBFC', surface: '#FFFFFF', surfaceBottom: '#FFFFFF',
    elevated: '#EDE7F8', accentSurface: '#EFE8FF', accentSurfaceBottom: '#EAE1FC',
    text: '#191326', muted: '#655C76', border: '#DED6EB', separator: '#E7E1EF',
    primary: '#6840B7', primaryBright: '#8054D4', accent: '#A63796', danger: '#B32F49',
    onPrimary: '#FFFFFF', heroText: '#191326', success: '#187653',
    trackOff: '#C9C1D5', nav: '#FCFAFF', heroArrow: '#6840B7', heroArrowInk: '#FFFFFF',
    heroSheen: '#B79AFF20', heroEdge: '#C9B7EB',
    cameraOverlay: '#FFFFFFF5', cameraControl: '#FFFFFFF0', cameraInk: '#191326', cameraFrame: '#B79AFF',
    welcomeGlow: ['#DCCCF8', '#F5F3FA00'] as const, welcomeArc: '#C2A7F2',
    cardShadow: '0 6px 20px rgba(38, 22, 65, 0.04)',
    quietShadow: '0 2px 8px rgba(38, 22, 65, 0.03)',
    primaryShadow: '0 6px 20px rgba(104, 64, 183, 0.15)',
    navShadow: '0 -3px 14px rgba(38, 22, 65, 0.04)',
    buttonGradient: ['#7950C5', '#6840B7'] as const,
    gradient: ['#EDE5FC', '#E5D9FA', '#F2EBFD'] as const,
    streamGradient: ['#F5F3FA', '#EDE6FA', '#F5F3FA'] as const,
  },
  dark: {
    background: '#090B10', pageGlow: '#11101C', surface: '#131720', surfaceBottom: '#131720',
    elevated: '#1A202C', accentSurface: '#241C37', accentSurfaceBottom: '#1D182C',
    text: '#F3F6FC', muted: '#A1ACBF', border: '#29313E', separator: '#242B38',
    primary: '#B79AFF', primaryBright: '#CFBAFF', accent: '#EC8BEA', danger: '#FF7F91',
    onPrimary: '#090B10', heroText: '#F3F6FC', success: '#65ECB1',
    trackOff: '#384151', nav: '#0D1017', heroArrow: '#B79AFF', heroArrowInk: '#090B10',
    heroSheen: '#B79AFF15', heroEdge: '#46355F',
    cameraOverlay: '#0D1017F5', cameraControl: '#131720EE', cameraInk: '#F3F6FC', cameraFrame: '#B79AFF',
    welcomeGlow: ['#2B2142', '#090B1000'] as const, welcomeArc: '#46355F',
    cardShadow: '0 6px 22px rgba(0, 0, 0, 0.16)',
    quietShadow: '0 2px 8px rgba(0, 0, 0, 0.10)',
    primaryShadow: '0 6px 24px rgba(183, 154, 255, 0.14)',
    navShadow: '0 -3px 16px rgba(0, 0, 0, 0.20)',
    buttonGradient: ['#C5ACFF', '#B79AFF'] as const,
    gradient: ['#241C37', '#302346', '#1A1726'] as const,
    streamGradient: ['#090B10', '#171224', '#090B10'] as const,
  },
};
export type Preferences = { theme: 'system' | 'light' | 'dark'; speak: boolean; guidance: boolean; vibration: boolean; largerText: boolean; highContrast: boolean; onboarded: boolean; voiceCommands: boolean; handsFreeQuestions: boolean; language: VoiceLanguage };
const defaults: Preferences = { theme: 'dark', speak: true, guidance: true, vibration: true, largerText: false, highContrast: false, onboarded: false, voiceCommands: true, handsFreeQuestions: true, language: voiceLanguage() };
const key = 'sora.preferences.v1';
const speechDefaultsVersion = 1;
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
          else if (name === 'language') { if (['en', 'ar', 'fr'].includes(saved.language)) next.language = saved.language; }
          else if (typeof saved[name] === 'boolean') next[name] = saved[name];
        }
        // Enable automatic answers once on upgrade; later mute choices still persist.
        if (saved.speechDefaultsVersion !== speechDefaultsVersion) next.speak = true;
        setPreferences(next);
      }
    } catch { if (mounted) setStorageError('Preferences could not be restored. Please select them again.'); }
    finally { if (mounted) setReady(true); }
  })(); return () => { mounted = false; }; }, []);
  const dark = (preferences.theme === 'system' ? system : preferences.theme) === 'dark';
  const base = palettes[dark ? 'dark' : 'light'];
  const colors = preferences.highContrast ? { ...base, muted: base.text, border: dark ? '#CFBAFF' : '#6840B7' } : base;
  useEffect(() => { if (ready && Platform.OS !== 'web') Appearance.setColorScheme(preferences.theme === 'system' ? 'auto' : preferences.theme); }, [preferences.theme, ready]);
  useEffect(() => { void SystemUI.setBackgroundColorAsync(colors.background).catch(() => {}); }, [colors.background]);
  useEffect(() => { if (ready && (fonts || fontError)) void SplashScreen.hideAsync().catch(() => {}); }, [ready, fonts, fontError]);
  useEffect(() => {
    if (!ready) return;
    const value = JSON.stringify({ ...preferences, speechDefaultsVersion });
    saveQueue.current = saveQueue.current.then(async () => {
      try { if (Platform.OS === 'web') localStorage.setItem(key, value); else await SecureStore.setItemAsync(key, value); }
      catch { setStorageError('Your changes apply now but could not be saved on this device.'); }
    });
  }, [preferences, ready]);
  const update = useCallback((value: Partial<Preferences>) => setPreferences(previous => ({ ...previous, ...value })), []);
  if (!ready || (!fonts && !fontError)) return null;
  return <Context.Provider value={{ preferences, update, colors, dark, storageError }}><StatusBar style={dark ? 'light' : 'dark'} /><NavigationBar style={dark ? 'light' : 'dark'} />{children}</Context.Provider>;
}
export function usePreferences() { const value = useContext(Context); if (!value) throw new Error('PreferencesProvider is missing'); return value; }

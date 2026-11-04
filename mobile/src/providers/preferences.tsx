import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Appearance, Platform, useColorScheme } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import * as SplashScreen from 'expo-splash-screen';
import * as SystemUI from 'expo-system-ui';
import { useFonts } from 'expo-font';
import { StatusBar } from 'expo-status-bar';
import { NavigationBar } from 'expo-navigation-bar';

void SplashScreen.preventAutoHideAsync().catch(() => {});
export const palettes = {
  light: {
    background: '#FBF2E8', pageGlow: '#FFFCF8', surface: '#FFFFFF', surfaceBottom: '#FFF9F2',
    elevated: '#FFF0DE', accentSurface: '#FFF0DD', accentSurfaceBottom: '#FFF8ED',
    text: '#35150A', muted: '#705143', border: '#F0DECE', separator: '#F2E5D8',
    primary: '#C94A05', primaryBright: '#F68A08', accent: '#E97907', danger: '#AD2734',
    onPrimary: '#FFFFFF', heroText: '#35150A', success: '#397C35',
    trackOff: '#DCCDBF', nav: '#FFFDF9', heroArrow: '#FFF2DD', heroArrowInk: '#993000',
    heroSheen: '#FFE0A77A', heroEdge: '#FFCE85',
    cameraOverlay: '#FFFAF0E8', cameraControl: '#FFFAF0EC', cameraInk: '#35150A', cameraFrame: '#FFFFFF',
    welcomeGlow: ['#FFE3B4', '#FFF8F000'] as const, welcomeArc: '#F5B45E',
    cardShadow: '0 7px 20px rgba(111, 59, 20, 0.10), 0 1px 3px rgba(111, 59, 20, 0.05)',
    quietShadow: '0 3px 10px rgba(111, 59, 20, 0.07)',
    primaryShadow: '0 8px 20px rgba(189, 65, 0, 0.23)',
    navShadow: '0 -5px 20px rgba(111, 59, 20, 0.06)',
    buttonGradient: ['#CB4B05', '#AE3400'] as const,
    gradient: ['#FFB63D', '#FF9408', '#E15903'] as const,
    streamGradient: ['#FFF9F1', '#FFE8C9', '#F6B665'] as const,
  },
  dark: {
    background: '#0D0703', pageGlow: '#241006', surface: '#241309', surfaceBottom: '#2B190D',
    elevated: '#3A210F', accentSurface: '#3A210F', accentSurfaceBottom: '#28150A',
    text: '#FFF5E0', muted: '#D7C1A7', border: '#58371F', separator: '#4D2D19',
    primary: '#FF9500', primaryBright: '#FFB339', accent: '#FFD066', danger: '#FFACA0',
    onPrimary: '#35150A', heroText: '#FFF5E0', success: '#B9D773',
    trackOff: '#64472F', nav: '#1A0D06', heroArrow: '#FFD16A', heroArrowInk: '#35150A',
    heroSheen: '#FFBD6040', heroEdge: '#C66B22',
    cameraOverlay: '#1B0C05E8', cameraControl: '#3A210FDD', cameraInk: '#FFF5E0', cameraFrame: '#FFE4AF',
    welcomeGlow: ['#7E340D', '#0D070300'] as const, welcomeArc: '#D76A13',
    cardShadow: '0 8px 22px rgba(0, 0, 0, 0.32), 0 1px 3px rgba(0, 0, 0, 0.19)',
    quietShadow: '0 3px 12px rgba(0, 0, 0, 0.22)',
    primaryShadow: '0 8px 22px rgba(255, 120, 0, 0.24)',
    navShadow: '0 -5px 20px rgba(0, 0, 0, 0.26)',
    buttonGradient: ['#FFB339', '#FF9500'] as const,
    gradient: ['#50240D', '#70300B', '#A74808'] as const,
    streamGradient: ['#1B0B04', '#4D220B', '#210D04'] as const,
  },
};
export type Preferences = { theme: 'system' | 'light' | 'dark'; speak: boolean; guidance: boolean; vibration: boolean; largerText: boolean; highContrast: boolean; onboarded: boolean; voiceCommands: boolean; handsFreeQuestions: boolean };
const defaults: Preferences = { theme: 'system', speak: true, guidance: true, vibration: true, largerText: false, highContrast: false, onboarded: false, voiceCommands: true, handsFreeQuestions: true };
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
  const colors = preferences.highContrast ? { ...base, muted: base.text, border: dark ? '#E4A64C' : '#8B3A13' } : base;
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

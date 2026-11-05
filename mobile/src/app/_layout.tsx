import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { VoiceCommandsProvider } from '@/providers/voice-commands';
import { AuthProvider } from '@/providers/auth';
import { PreferencesProvider, usePreferences } from '@/providers/preferences';
export const unstable_settings = { initialRouteName: '(tabs)' };
function Navigation() {
  const { colors, dark } = usePreferences();
  const base = dark ? DarkTheme : DefaultTheme;
  const theme = { ...base, colors: { ...base.colors, background: colors.background, card: colors.nav, text: colors.text, primary: colors.primary, border: colors.border, notification: colors.accent } };
  return <ThemeProvider value={theme}><Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }} /></ThemeProvider>;
}
export default function Layout() { return <PreferencesProvider><AuthProvider><VoiceCommandsProvider><Navigation /></VoiceCommandsProvider></AuthProvider></PreferencesProvider>; }

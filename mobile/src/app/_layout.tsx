import { Stack } from 'expo-router';
import { VoiceCommandsProvider } from '@/providers/voice-commands';
import { AuthProvider } from '@/providers/auth';
import { PreferencesProvider, usePreferences } from '@/providers/preferences';
function Navigation() { const { colors } = usePreferences(); return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }} />; }
export default function Layout() { return <PreferencesProvider><AuthProvider><VoiceCommandsProvider><Navigation /></VoiceCommandsProvider></AuthProvider></PreferencesProvider>; }

import { Stack } from 'expo-router';
import { usePreferences } from '@/providers/preferences';
/** Web retains the accessible app navigation rendered by each page. */
export default function AppTabs() {
  const { colors } = usePreferences();
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }} />;
}

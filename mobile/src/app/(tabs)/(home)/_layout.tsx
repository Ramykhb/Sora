import { Stack } from 'expo-router';
import { usePreferences } from '@/providers/preferences';
export default function HomeLayout() {
  const { colors } = usePreferences();
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }} />;
}

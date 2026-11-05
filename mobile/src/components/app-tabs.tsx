import { useMemo, useState } from 'react';
import { DynamicColorIOS, Platform } from 'react-native';
import { Stack } from 'expo-router';
import { NativeTabs } from 'expo-router/native-tabs';
import { useAuth } from '@/providers/auth';
import { palettes, usePreferences } from '@/providers/preferences';
import { TabBarContext } from '@/providers/tab-bar';

export default function AppTabs() {
  const { colors, preferences } = usePreferences();
  const { tokens } = useAuth();
  const [fullscreen, setFullscreen] = useState(false);
  const context = useMemo(() => ({ native: true, setFullscreen }), []);
  if (Platform.OS !== 'ios') return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }} />;
  const selected = DynamicColorIOS({ dark: palettes.dark.primary, light: palettes.light.primary });
  const normal = DynamicColorIOS({ dark: preferences.highContrast ? palettes.dark.text : palettes.dark.muted, light: preferences.highContrast ? palettes.light.text : palettes.light.muted });
  // UIKit supplies Liquid Glass on iOS 26+ and its standard tab bar on older iOS.
  return <TabBarContext.Provider value={context}><NativeTabs
    hidden={!tokens || !preferences.onboarded || fullscreen}
    minimizeBehavior="never"
    backgroundColor={colors.nav}
    tintColor={selected}
    iconColor={{ default: normal, selected }}
    labelStyle={{ default: { color: normal, fontSize: 11 }, selected: { color: selected, fontSize: 11, fontWeight: '600' } }}>
    <NativeTabs.Trigger name="(home)" disableAutomaticContentInsets contentStyle={{ backgroundColor: colors.background }} accessibilityLabel="Home">
      <NativeTabs.Trigger.Label>Home</NativeTabs.Trigger.Label>
      <NativeTabs.Trigger.Icon sf={{ default: 'house', selected: 'house.fill' }} />
    </NativeTabs.Trigger>
    <NativeTabs.Trigger name="camera" disableAutomaticContentInsets contentStyle={{ backgroundColor: colors.background }} accessibilityLabel="Assist">
      <NativeTabs.Trigger.Label>Assist</NativeTabs.Trigger.Label>
      <NativeTabs.Trigger.Icon sf={{ default: 'camera', selected: 'camera.fill' }} />
    </NativeTabs.Trigger>
    <NativeTabs.Trigger name="explore" disableAutomaticContentInsets contentStyle={{ backgroundColor: colors.background }} accessibilityLabel="History">
      <NativeTabs.Trigger.Label>History</NativeTabs.Trigger.Label>
      <NativeTabs.Trigger.Icon sf={{ default: 'clock', selected: 'clock.fill' }} />
    </NativeTabs.Trigger>
    <NativeTabs.Trigger name="settings" disableAutomaticContentInsets contentStyle={{ backgroundColor: colors.background }} accessibilityLabel="Settings">
      <NativeTabs.Trigger.Label>Settings</NativeTabs.Trigger.Label>
      <NativeTabs.Trigger.Icon sf={{ default: 'gearshape', selected: 'gearshape.fill' }} />
    </NativeTabs.Trigger>
  </NativeTabs></TabBarContext.Provider>;
}

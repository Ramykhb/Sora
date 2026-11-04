import { useCallback, useRef, useState } from 'react';
import { AccessibilityInfo, Image, Pressable, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useFocusEffect } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import { useVoiceCommands } from '@/providers/voice-commands';
import { speech } from '@/lib/speech';
import { AuthScreen } from '@/components/auth-screen';
import { Welcome } from '@/components/welcome';
import { BottomNav, Icon, Label, Tap } from '@/components/sora-ui';

export default function Home() {
  const { preferences } = usePreferences();
  const { tokens } = useAuth();
  if (!preferences.onboarded) return <Welcome />;
  return tokens ? <StartStreamHome /> : <AuthScreen />;
}

function StartStreamHome() {
  const { colors, preferences, dark } = usePreferences();
  const [smallScreen, setSmallScreen] = useState(false);
  const compact = smallScreen || preferences.largerText;
  const voice = useVoiceCommands();
  const starting = useRef(false);
  useFocusEffect(useCallback(() => {
    let cancelled = false;
    starting.current = false;
    if (preferences.guidance) {
      // VoiceOver/TalkBack already announce the large accessible button.
      void AccessibilityInfo.isScreenReaderEnabled().then(enabled => {
        if (!cancelled && !enabled) return speech.answer('Tap anywhere in the main area to start your stream. More tools and settings are at the bottom.', 'en');
      }).catch(() => {});
    }
    return () => { cancelled = true; void speech.stop(); };
  }, [preferences.guidance]));

  function startStream() {
    if (starting.current) return;
    starting.current = true;
    void speech.stop();
    // Use the same permission, consent, session and streaming flow as Hey Sora.
    router.navigate({ pathname: '/camera', params: { mode: 'live', voiceStart: String(Date.now()) } });
  }

  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
    <Pressable
      accessible
      accessibilityRole="button"
      accessibilityLabel="Start live stream"
      accessibilityHint="Starts your camera for live assistance. Activating agrees to camera processing and storing selected images and conversations until the session expires."
      onPress={startStream}
      onLayout={event => setSmallScreen(event.nativeEvent.layout.height < 620)}
      style={({ pressed }) => ({ flex: 1, backgroundColor: colors.background, opacity: pressed ? 0.9 : 1 })}
    >
      <LinearGradient pointerEvents="none" colors={colors.streamGradient} locations={[0, 0.56, 1]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0 }} />
      <View pointerEvents="none" style={{ position: 'absolute', top: -140, left: -100, right: -110, height: 280, borderRadius: 250, borderBottomWidth: 2, borderColor: colors.welcomeArc, opacity: dark ? 0.8 : 0.5, transform: [{ rotate: '-18deg' }] }} />
      <View pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{ flex: 1, alignItems: 'center', justifyContent: 'space-between', padding: compact ? 16 : 28, gap: compact ? 9 : 18 }}>
        <Label bold size={17} style={{ color: colors.heroText, letterSpacing: 7 }}>SORA</Label>
        <View style={{ alignItems: 'center', gap: compact ? 10 : 17 }}>
          <Image source={require('../../assets/images/sora-ribbon.png')} style={{ width: compact ? 86 : 114, height: compact ? 84 : 112 }} resizeMode="contain" />
          <View style={{ width: compact ? 74 : 94, height: compact ? 74 : 94, borderRadius: 47, borderWidth: 2, borderColor: colors.heroEdge, backgroundColor: colors.heroArrow, alignItems: 'center', justifyContent: 'center', boxShadow: colors.primaryShadow }}><Icon name="camera-outline" color={colors.heroArrowInk} size={compact ? 34 : 44} /></View>
          <Label bold size={compact ? 24 : 29} style={{ color: colors.heroText, textAlign: 'center' }}>Tap anywhere{'\n'}to start streaming</Label>
          <Label size={14} style={{ color: colors.heroText, textAlign: 'center' }}>The whole area is your start button.</Label>
          <Label size={12} style={{ color: colors.heroText, textAlign: 'center' }}>Using a screen reader? Focus Start live stream, then double-tap to begin.</Label>
        </View>
        <View style={{ gap: 10, alignItems: 'center' }}>
          {preferences.voiceCommands && <Label size={12} style={{ color: colors.heroText, textAlign: 'center' }}>{voice.status}</Label>}
          <Label size={11} style={{ color: colors.heroText, textAlign: 'center' }}>Starting allows camera processing. Selected images and conversations are stored until your session expires.</Label>
        </View>
      </View>
    </Pressable>
    <View style={{ backgroundColor: colors.nav }}>
      <Tap label="More tools, read text and recent activity" onPress={() => router.push('./tools')} style={{ alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 10, minHeight: 56, borderTopWidth: 1, borderColor: colors.border }}><Icon name="grid-outline" size={20} /><Label bold size={14}>More tools</Label></Tap>
      <BottomNav />
    </View>
  </SafeAreaView>;
}

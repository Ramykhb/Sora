import { useCallback, useRef, useState } from 'react';
import { AccessibilityInfo, Pressable, ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import { useVoiceCommands } from '@/providers/voice-commands';
import { speech } from '@/lib/speech';
import { AuthScreen } from '@/components/auth-screen';
import { Welcome } from '@/components/welcome';
import { SoraHero, SoraLogo } from '@/components/brand';
import { BottomNav, Icon, Label, ScreenSafeArea, Tap } from '@/components/sora-ui';

export default function Home() {
  const { preferences } = usePreferences();
  const { tokens } = useAuth();
  if (!preferences.onboarded) return <Welcome />;
  return tokens ? <StartStreamHome /> : <AuthScreen />;
}

function StartStreamHome() {
  const { colors, preferences } = usePreferences();
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

  return <ScreenSafeArea style={{ flex: 1, backgroundColor: colors.background }}>
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ flexGrow: 1 }} onLayout={event => setSmallScreen(event.nativeEvent.layout.height < 620)}><Pressable
      accessible
      accessibilityRole="button"
      accessibilityLabel="Start live stream"
      accessibilityHint="Starts your camera for live assistance. Activating agrees to camera processing and storing selected images and conversations until the session expires."
      onPress={startStream}
      style={({ pressed }) => ({ flex: 1, backgroundColor: colors.background, opacity: pressed ? 0.9 : 1 })}
    >
      <LinearGradient pointerEvents="none" colors={colors.streamGradient} locations={[0, 0.56, 1]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0 }} />
      <View pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{ flex: 1, width: '100%', maxWidth: 600, alignSelf: 'center', justifyContent: 'space-between', padding: compact ? 20 : 28, gap: 12 }}>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, alignItems: 'center', justifyContent: 'space-between' }}><SoraLogo size={36} wordmark /><View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', gap: 6, alignItems: 'center' }}><Icon name="sparkles-outline" size={13} /><Label muted size={10}>YOUR AI COMPANION</Label></View></View>
        <View style={{ alignItems: 'center', gap: compact ? 8 : 14 }}>
          <SoraHero size={compact ? 110 : 248} />
          <Label bold size={10} style={{ color: colors.primary, letterSpacing: 2 }}>SEE BEYOND.</Label>
          <Label bold size={compact ? 26 : 34} style={{ textAlign: 'center', letterSpacing: -1 }}>Your world,{'\n'}spoken clearly.</Label>
          <Label muted size={compact ? 13 : 14} style={{ textAlign: 'center', maxWidth: 290 }}>Point your camera. Hear what’s around you. Ask anything.</Label>
          <View style={{ flexDirection: 'row', gap: 8, maxWidth: '100%', backgroundColor: colors.primary, borderRadius: 14, paddingHorizontal: 18, paddingVertical: 17, alignItems: 'center', marginTop: 6 }}><Icon name="camera-outline" color={colors.onPrimary} size={22} /><Label bold size={15} style={{ color: colors.onPrimary, flexShrink: 1, textAlign: 'center' }}>Tap anywhere to start</Label><Icon name="arrow-forward" color={colors.onPrimary} size={18} /></View>
          <Label muted size={11} style={{ textAlign: 'center' }}>Using a screen reader? Focus Start live stream, then double-tap.</Label>
        </View>
        <View style={{ gap: 10, alignItems: 'center' }}>
          {preferences.voiceCommands && <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><Icon name="mic-outline" color={colors.accent} size={16} /><Label size={12} style={{ color: colors.muted, flexShrink: 1 }}>{voice.status}</Label></View>}
          <Label muted size={10} style={{ textAlign: 'center' }}>Starting allows camera processing. Selected images and conversations are stored until your session expires.</Label>
        </View>
      </View>
    </Pressable></ScrollView>
    <View style={{ backgroundColor: colors.nav }}>
      <Tap label="More tools, read text and recent activity" onPress={() => router.push('./tools')} style={{ alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 10, minHeight: 56, borderTopWidth: 1, borderColor: colors.border }}><Icon name="grid-outline" size={20} /><Label bold size={14}>More tools</Label></Tap>
      <BottomNav />
    </View>
  </ScreenSafeArea>;
}

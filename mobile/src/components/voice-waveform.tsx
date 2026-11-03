import { useEffect, useState, useSyncExternalStore } from 'react';
import { AccessibilityInfo, Animated, Easing, View } from 'react-native';
import { voiceLevel } from '@/lib/voice-level';
import { usePreferences } from '@/providers/preferences';
import { Icon, Label } from './sora-ui';

const barWeights = [0.22, 0.36, 0.55, 0.32, 0.68, 0.85, 0.51, 0.93, 0.7, 1, 0.7, 0.93, 0.51, 0.85, 0.68, 0.32, 0.55, 0.36, 0.22];

export function VoiceWaveform({ commandsOnly = false }: { commandsOnly?: boolean }) {
  const { colors, preferences } = usePreferences();
  const { listening, level } = useSyncExternalStore(voiceLevel.subscribe, voiceLevel.getSnapshot, voiceLevel.getSnapshot);
  const [amplitude] = useState(() => new Animated.Value(0));
  const [reduceMotion, setReduceMotion] = useState(false);
  const enabled = preferences.voiceCommands;
  const target = enabled && listening ? level : 0;
  useEffect(() => {
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then(value => { if (mounted) setReduceMotion(value); }).catch(() => {});
    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => { mounted = false; subscription.remove(); };
  }, []);
  useEffect(() => {
    const animation = Animated.timing(amplitude, { toValue: target, duration: reduceMotion ? 0 : target === 0 ? 180 : 75, easing: Easing.linear, useNativeDriver: true, isInteraction: false });
    animation.start();
    return () => animation.stop();
  }, [amplitude, target, reduceMotion]);
  const label = !enabled ? 'Microphone off' : !listening ? 'Microphone idle' : commandsOnly ? 'Hey Sora commands only' : 'Listening for your voice';
  return <View accessible accessibilityLabel={label} style={{ gap: 4, borderRadius: 20, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 16, paddingVertical: 9 }}>
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
      <Icon name={enabled && listening ? 'mic-outline' : 'mic-off-outline'} size={21} color={enabled && listening ? colors.primary : colors.muted} />
      <View style={{ flex: 1, height: 38, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
        {barWeights.map((weight, index) => <Animated.View key={index} style={{ width: 4, height: 34, borderRadius: 2, backgroundColor: enabled && listening ? colors.primary : colors.muted, opacity: enabled && listening ? 1 : 0.4, transform: [{ scaleY: amplitude.interpolate({ inputRange: [0, 1], outputRange: [0.1, weight], extrapolate: 'clamp' }) }] }} />)}
      </View>
    </View>
    <Label muted size={11} style={{ textAlign: 'center' }}>{label}</Label>
  </View>;
}

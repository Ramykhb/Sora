import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { AccessibilityInfo, Animated, Easing, StyleSheet, View } from 'react-native';
import { voiceLevel } from '@/lib/voice-level';
import { usePreferences } from '@/providers/preferences';
import { Icon, Label } from './sora-ui';

const WAVE_HEIGHT = 104;
// A tapered speech envelope with several uneven bursts and a dominant center.
// Only the envelope is illustrative; its amplitude follows the actual microphone.
const spikeWeights = Array.from({ length: 73 }, (_, index) => {
  const x = index / 72;
  const burst = (center: number, width: number) => Math.exp(-(((x - center) / width) ** 2));
  const envelope = 0.28 * burst(0.08, 0.045) + 0.64 * burst(0.26, 0.075)
    + burst(0.5, 0.075) + 0.55 * burst(0.74, 0.07) + 0.25 * burst(0.9, 0.04);
  const detail = 0.5 + 0.5 * Math.abs(Math.cos(index * 1.83));
  return Math.max(0.035, envelope * detail);
});

export function VoiceWaveform({ commandsOnly = false }: { commandsOnly?: boolean }) {
  const { colors, preferences } = usePreferences();
  const { listening, level } = useSyncExternalStore(voiceLevel.subscribe, voiceLevel.getSnapshot, voiceLevel.getSnapshot);
  const [amplitude] = useState(() => new Animated.Value(0));
  const spikes = useMemo(() => spikeWeights.map(weight => amplitude.interpolate({
    inputRange: [0, 0.2, 0.6, 1],
    outputRange: [0.018, Math.max(0.018, weight * 0.25), Math.max(0.018, weight * 0.66), weight],
    extrapolate: 'clamp',
  })), [amplitude]);
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
  const color = enabled && listening ? colors.primary : colors.muted;
  return <View accessible accessibilityLabel={label} style={{ gap: 6, borderRadius: 20, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 16, paddingVertical: 12 }}>
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={styles.wave}>
      <View style={[styles.centerline, { backgroundColor: color }]} />
      {spikes.map((scaleY, index) => <View key={index} style={styles.column}>
        <Animated.View style={{ opacity: enabled && listening ? 1 : 0.4, transform: [{ scaleY }] }}>
          <View style={[styles.point, { borderBottomWidth: WAVE_HEIGHT / 2, borderBottomColor: color }]} />
          <View style={[styles.point, { borderTopWidth: WAVE_HEIGHT / 2, borderTopColor: color }]} />
        </Animated.View>
      </View>)}
    </View>
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={styles.caption}>
      <Icon name={enabled && listening ? 'mic-outline' : 'mic-off-outline'} size={14} color={color} />
      <Label muted size={11}>{label}</Label>
    </View>
  </View>;
}

const styles = StyleSheet.create({
  wave: { height: WAVE_HEIGHT, flexDirection: 'row', alignItems: 'center', overflow: 'hidden' },
  column: { flex: 1, height: WAVE_HEIGHT, alignItems: 'center', justifyContent: 'center' },
  point: { width: 0, height: 0, borderLeftWidth: 1.25, borderRightWidth: 1.25, borderLeftColor: 'transparent', borderRightColor: 'transparent' },
  centerline: { position: 'absolute', left: 0, right: 0, top: WAVE_HEIGHT / 2, height: StyleSheet.hairlineWidth, opacity: 0.2 },
  caption: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6 },
});

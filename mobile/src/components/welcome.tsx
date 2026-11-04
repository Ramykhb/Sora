import { Image, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useState } from 'react';
import { usePreferences } from '@/providers/preferences';
import { Label, Page, Primary, Tap } from './sora-ui';
const slides = [
  ['Your AI accessibility assistant.', 'Describe your surroundings, read text, and get real-time guidance — all with your voice.'],
  ['Understand your surroundings.', 'Point your camera and hear a clear description of what is around you.'],
  ['A world of words, read aloud.', 'Scan text, listen to it, and revisit your saved moments whenever you need.'],
];
export function Welcome() {
  const { colors, dark, update } = usePreferences();
  const [slide, setSlide] = useState(0);
  return <Page><View style={{ flex: 1, justifyContent: 'space-between', gap: 32 }}>
    <View style={{ alignItems: 'center', paddingTop: 54, paddingBottom: 28 }}>
      <LinearGradient pointerEvents="none" colors={colors.welcomeGlow} style={{ position: 'absolute', top: -60, left: -70, right: -70, height: 300, borderBottomRightRadius: 230, transform: [{ rotate: '-17deg' }] }} />
      <View pointerEvents="none" style={{ position: 'absolute', top: -32, left: -70, right: -70, height: 210, borderRadius: 180, borderTopWidth: 1.5, borderColor: colors.welcomeArc, opacity: dark ? 0.8 : 0.55, transform: [{ rotate: '-24deg' }] }} />
      <Image source={require('../../assets/images/sora-ribbon.png')} style={{ width: 166, height: 166 }} resizeMode="contain" accessibilityLabel="SORA amber ribbon logo" />
      <Label bold size={37} style={{ letterSpacing: 12, paddingLeft: 12, marginTop: 6 }}>SORA</Label>
      <Label size={16} style={{ letterSpacing: 3, color: colors.primary }}>See beyond.</Label>
    </View>
    <View style={{ gap: 17, paddingHorizontal: 14 }}><Label bold size={25}>{slides[slide][0]}</Label><Label muted size={17}>{slides[slide][1]}</Label></View>
    <View style={{ gap: 34, paddingBottom: 12 }}><View style={{ flexDirection: 'row', alignSelf: 'center' }}>{slides.map((_, index) => <Tap key={index} label={`Introduction ${index + 1} of 3`} selected={slide === index} onPress={() => setSlide(index)} style={{ minWidth: 24, alignItems: 'center', justifyContent: 'center' }}><View style={{ width: 9, height: 9, borderRadius: 5, backgroundColor: slide === index ? colors.primary : colors.trackOff }} /></Tap>)}</View><Primary title="Get Started" onPress={() => update({ onboarded: true })} /></View>
  </View></Page>;
}

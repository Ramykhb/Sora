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
    <View style={{ alignItems: 'center', paddingTop: 60, paddingBottom: 25 }}>
      <LinearGradient pointerEvents="none" colors={dark ? ['#0A2A4A', '#060A1000'] : ['#D1F3FF', '#E8F0F900']} style={{ position: 'absolute', top: -80, left: -80, right: -80, height: 300, borderBottomRightRadius: 240, transform: [{ rotate: '-18deg' }] }} />
      <View pointerEvents="none" style={{ position: 'absolute', top: -70, left: -115, width: 520, height: 280, borderRadius: 180, borderTopWidth: 1, borderColor: dark ? '#24527A' : '#BFDEEF', transform: [{ rotate: '-24deg' }] }} />
      <Image source={require('../../assets/images/sora-ribbon.png')} style={{ width: 170, height: 174 }} resizeMode="contain" accessibilityLabel="SORA colorful ribbon logo" />
      <Label bold size={37} style={{ letterSpacing: 13, paddingLeft: 13, marginTop: 8 }}>SORA</Label>
      <Label size={17} style={{ letterSpacing: 3, color: dark ? colors.muted : '#3878B3' }}>See beyond.</Label>
    </View>
    <View style={{ gap: 17, paddingHorizontal: 14 }}><Label bold size={25}>{slides[slide][0]}</Label><Label muted size={17}>{slides[slide][1]}</Label></View>
    <View style={{ gap: 36, paddingBottom: 12 }}><View style={{ flexDirection: 'row', alignSelf: 'center' }}>{slides.map((_, index) => <Tap key={index} label={`Introduction ${index + 1} of 3`} selected={slide === index} onPress={() => setSlide(index)} style={{ minWidth: 24, alignItems: 'center', justifyContent: 'center' }}><View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: slide === index ? colors.primary : dark ? '#4C5664' : '#BFCFE4' }} /></Tap>)}</View><Primary title="Get Started" onPress={() => update({ onboarded: true })} /></View>
  </View></Page>;
}

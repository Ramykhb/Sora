import { View } from 'react-native';
import { useState } from 'react';
import { usePreferences } from '@/providers/preferences';
import { SoraHero, SoraLogo } from './brand';
import { Icon, Label, Page, Primary, Tap } from './sora-ui';
const slides = [
  { icon: 'eye-outline', title: 'Your world, spoken clearly.', copy: 'Meet Sora. Describe your surroundings, read text, and ask questions with your voice.' },
  { icon: 'camera-outline', title: 'A little more clarity. Anywhere.', copy: 'Point your camera and hear what is around you. Start live assistance with one simple tap.' },
  { icon: 'reader-outline', title: 'Every detail. In your own words.', copy: 'Listen to printed text, ask about a scene, and revisit your saved moments when you need them.' },
] as const;
export function Welcome() {
  const { colors, update } = usePreferences();
  const [slide, setSlide] = useState(0);
  return <Page><View style={{ flex: 1, justifyContent: 'space-between', gap: 20 }}>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center', paddingTop: 12 }}><SoraLogo size={38} wordmark /><Label muted size={11}>MADE FOR YOUR EVERYDAY</Label></View>
    <View style={{ alignItems: 'center' }}><SoraHero size={260} /></View>
    <View style={{ gap: 16 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><Icon name={slides[slide].icon} size={17} /><Label bold size={10} style={{ color: colors.primary, letterSpacing: 2 }}>SEE BEYOND</Label></View><Label accessibilityRole="header" bold size={32} style={{ letterSpacing: -1 }}>{slides[slide].title}</Label><Label muted size={15}>{slides[slide].copy}</Label></View>
    <View style={{ gap: 16, paddingBottom: 12 }}><View style={{ flexDirection: 'row', alignSelf: 'center' }}>{slides.map((_, index) => <Tap key={index} label={`Introduction ${index + 1} of 3`} selected={slide === index} onPress={() => setSlide(index)} style={{ minWidth: 36, alignItems: 'center', justifyContent: 'center' }}><View style={{ width: slide === index ? 24 : 7, height: 7, borderRadius: 5, backgroundColor: slide === index ? colors.primary : colors.trackOff }} /></Tap>)}</View><Primary title={slide === 2 ? 'Get started' : 'Continue'} onPress={() => slide === 2 ? update({ onboarded: true }) : setSlide(slide + 1)} />{slide < 2 && <Tap label="Skip introduction" onPress={() => update({ onboarded: true })} style={{ alignItems: 'center', justifyContent: 'center' }}><Label muted size={12}>Skip introduction</Label></Tap>}</View>
  </View></Page>;
}

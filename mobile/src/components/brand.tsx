import { Image, View } from 'react-native';
import { Label } from './sora-ui';
import { usePreferences } from '@/providers/preferences';
/** Shared Sora Buddy mark, exported from brand/sora-logo.svg. */
export function SoraLogo({ size = 40, wordmark = false }: { size?: number; wordmark?: boolean }) {
  const { dark } = usePreferences();
  return <View accessible accessibilityLabel="Sora" style={{ flexDirection: 'row', alignItems: 'center', gap: 11 }}><Image accessibilityElementsHidden importantForAccessibility="no-hide-descendants" source={dark ? require('../../assets/brand/sora-logo.png') : require('../../assets/brand/sora-logo-light.png')} style={{ width: size, height: size }} />{wordmark && <Label bold size={Math.round(size * 0.68)} style={{ letterSpacing: -1 }}>sora</Label>}</View>;
}
export function SoraHero({ size = 240 }: { size?: number }) {
  const { dark } = usePreferences();
  return <Image accessible={false} source={dark ? require('../../assets/brand/sora-hero.png') : require('../../assets/brand/sora-hero-light.png')} style={{ width: size, height: size }} resizeMode="contain" />;
}
export function ScreenIntro({ eyebrow, title, subtitle }: { eyebrow?: string; title: string; subtitle?: string }) {
  const { colors } = usePreferences();
  return <View style={{ gap: 6, marginBottom: 6 }}>{eyebrow && <Label size={10} bold style={{ color: colors.primary, letterSpacing: 1.6 }}>{eyebrow.toUpperCase()}</Label>}<Label accessibilityRole="header" bold size={27}>{title}</Label>{subtitle && <Label muted size={13}>{subtitle}</Label>}</View>;
}

import type { ComponentProps, ReactNode } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View, type TextProps, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';
import { usePreferences } from '@/providers/preferences';

export type IconName = ComponentProps<typeof Ionicons>['name'];
export const layoutTokens = { pageInset: 20, sectionGap: 18, cardRadius: 18, cardPadding: 20, buttonRadius: 14 } as const;
export function Icon({ name, size = 26, color }: { name: IconName; size?: number; color?: string }) {
  const { colors } = usePreferences(); return <Ionicons accessible={false} name={name} size={size} color={color || colors.primary} />;
}
export function Label({ children, size = 15, bold, muted, style, ...props }: TextProps & { size?: number; bold?: boolean; muted?: boolean }) {
  const { colors, preferences } = usePreferences();
  const scale = preferences.largerText ? 1.2 : 1;
  return <Text {...props} style={[{ fontFamily: 'Sora', fontSize: size * scale, lineHeight: size * scale * (bold && size >= 18 ? 1.36 : 1.5), letterSpacing: bold ? size >= 18 ? -0.45 : -0.1 : 0, color: muted ? colors.muted : colors.text, fontWeight: bold ? '600' : '400' }, style]}>{children}</Text>;
}
export function Tap({ children, onPress, label, style, disabled, selected, expanded }: { children: ReactNode; onPress: () => void; label: string; style?: ViewStyle | ViewStyle[]; disabled?: boolean; selected?: boolean; expanded?: boolean }) {
  const { preferences } = usePreferences();
  return <Pressable accessibilityRole="button" accessibilityLabel={label} aria-disabled={!!disabled} aria-selected={selected} aria-expanded={expanded} accessibilityState={{ disabled: !!disabled, ...(selected === undefined ? {} : { selected }), ...(expanded === undefined ? {} : { expanded }) }} disabled={disabled} onPress={() => { if (preferences.vibration) void Haptics.selectionAsync().catch(() => {}); onPress(); }} style={({ pressed }) => [{ minWidth: 48, minHeight: 48, opacity: disabled ? 0.45 : pressed ? 0.75 : 1 }, style]}>{children}</Pressable>;
}
export function Card({ children, style, tone = 'default' }: { children: ReactNode; style?: ViewStyle; tone?: 'default' | 'accent' | 'quiet' }) {
  const { colors } = usePreferences();
  const top = style?.backgroundColor || (tone === 'accent' ? colors.accentSurface : colors.surface);
  const bottom = style?.backgroundColor || (tone === 'accent' ? colors.accentSurfaceBottom : colors.surfaceBottom);
  return <View style={[styles.card, { backgroundColor: top, borderColor: colors.border, boxShadow: tone === 'quiet' ? colors.quietShadow : colors.cardShadow }, style]}>
    <LinearGradient pointerEvents="none" colors={[top, bottom]} start={{ x: 0, y: 0 }} end={{ x: 0.8, y: 1 }} style={{ position: 'absolute', top: 1, bottom: 1, left: 1, right: 1, borderRadius: layoutTokens.cardRadius - 1, zIndex: Platform.OS === 'web' ? -1 : 0 }} />
    {children}
  </View>;
}
export function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (value: boolean) => void }) {
  const { colors, preferences } = usePreferences();
  function toggle() { if (preferences.vibration) void Haptics.selectionAsync().catch(() => {}); onChange(!value); }
  const keyboard: Pick<ComponentProps<typeof Pressable>, 'onKeyDown'> = Platform.OS === 'web' ? { onKeyDown: event => { if ('key' in event && event.key === ' ') { event.preventDefault(); toggle(); } } } : {};
  return <Pressable {...keyboard} accessibilityRole="switch" accessibilityLabel={label} aria-checked={value} accessibilityState={{ checked: value }} onPress={toggle} style={{ minWidth: 50, minHeight: 48, alignItems: 'center', justifyContent: 'center' }}><View style={{ width: 48, height: 28, padding: 3, borderRadius: 16, backgroundColor: value ? colors.primary : colors.trackOff, alignItems: value ? 'flex-end' : 'flex-start', borderWidth: 1, borderColor: value ? colors.primaryBright : colors.border }}><View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: '#FFFFFF', boxShadow: '0 1px 3px rgba(0,0,0,0.20)' }} /></View></Pressable>;
}
export function Primary({ title, onPress, disabled }: { title: string; onPress: () => void; disabled?: boolean }) {
  const { colors } = usePreferences();
  return <Tap label={title} onPress={onPress} disabled={disabled} style={{ borderRadius: layoutTokens.buttonRadius, boxShadow: colors.primaryShadow }}><LinearGradient colors={colors.buttonGradient} style={{ minHeight: 58, borderRadius: layoutTokens.buttonRadius, borderWidth: 1, borderColor: colors.heroEdge, paddingHorizontal: 24, paddingVertical: 16, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 15, overflow: 'hidden' }}><LinearGradient pointerEvents="none" colors={['#FFFFFF30', '#FFFFFF00']} style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 24 }} /><Label bold style={{ color: colors.onPrimary }}>{title}</Label><Icon name="arrow-forward" size={21} color={colors.onPrimary} /></LinearGradient></Tap>;
}
export function Header({ title }: { title: string }) {
  const { colors } = usePreferences();
  return <View style={styles.header}><Tap label="Go back" onPress={() => router.canGoBack() ? router.back() : router.replace('/')} style={{ alignItems: 'center', justifyContent: 'center', borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, boxShadow: colors.quietShadow }}><Icon name="chevron-back" color={colors.text} size={23} /></Tap><Label bold size={18} style={{ flex: 1, textAlign: 'center' }}>{title}</Label><View style={{ width: 48 }} /></View>;
}
export function Page({ children, title, footer }: { children: ReactNode; title?: string; footer?: ReactNode }) {
  const { colors } = usePreferences();
  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}><LinearGradient pointerEvents="none" colors={[colors.pageGlow, colors.background]} style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 340 }} />{title && <Header title={title} />}<ScrollView showsVerticalScrollIndicator={false} showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>{children}</ScrollView>{footer}</SafeAreaView>;
}
export function BottomNav({ active = 'Home' }: { active?: string }) {
  const { colors } = usePreferences();
  const tabs = [{ label: 'Home', icon: 'home-outline', route: '/' }, { label: 'Assist', icon: 'camera-outline', route: '/camera' }, { label: 'History', icon: 'reader-outline', route: '/explore' }, { label: 'Settings', icon: 'settings-outline', route: '/settings' }] as const;
  return <View style={[styles.nav, { backgroundColor: colors.nav, borderColor: colors.border, boxShadow: colors.navShadow }]}>{tabs.map(tab => <Tap key={tab.label} selected={active === tab.label} label={tab.label} onPress={() => router.push(tab.route)} style={styles.tab}><View style={{ width: 52, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: active === tab.label ? colors.accentSurface : 'transparent' }}><Icon name={active === tab.label && tab.label === 'Home' ? 'home' : tab.icon} size={23} color={active === tab.label ? colors.primary : colors.muted} /></View><Label size={10} bold={active === tab.label} style={{ color: active === tab.label ? colors.primary : colors.muted }}>{tab.label}</Label></Tap>)}</View>;
}
export const styles = StyleSheet.create({
  content: { padding: layoutTokens.pageInset, gap: layoutTokens.sectionGap, paddingBottom: 32, flexGrow: 1, width: '100%', maxWidth: 640, alignSelf: 'center' },
  card: { borderRadius: layoutTokens.cardRadius, borderWidth: 1, padding: layoutTokens.cardPadding, gap: 12, zIndex: 0 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12 },
  nav: { flexDirection: 'row', borderTopWidth: 1, paddingTop: 10, paddingBottom: 8, paddingHorizontal: 8 },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 4 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 14 },
});

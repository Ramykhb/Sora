import { usePreferences } from '@/providers/preferences';
import { Pressable, StyleSheet, Text, TextInput, type TextInputProps } from 'react-native';
export function Action({ title, onPress, disabled = false, variant = 'secondary' }: { title: string; onPress: () => void; disabled?: boolean; variant?: 'primary' | 'secondary' | 'danger' }) {
  const ui = useUI();
  const { colors } = usePreferences();
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={({ pressed }) => [ui.button, variant === 'danger' && { borderColor: colors.danger }, variant === 'primary' && { backgroundColor: colors.primary, borderColor: colors.primary, boxShadow: colors.primaryShadow }, { opacity: disabled ? 0.45 : pressed ? 0.82 : 1 }]}><Text style={[ui.buttonText, variant === 'danger' && { color: colors.danger }, variant === 'primary' && { color: colors.onPrimary }]}>{title}</Text></Pressable>;
}
export function Field(props: TextInputProps) {
  const ui = useUI();
  const { colors } = usePreferences();
  return <TextInput placeholderTextColor={colors.muted} {...props} accessibilityLabel={props.accessibilityLabel || props.placeholder} style={[ui.input, props.style]} />;
}
export function useUI() {
  const { colors: c, preferences: p } = usePreferences();
  return StyleSheet.create({
  screen: { flex: 1, backgroundColor: c.background },
  content: { padding: 22, gap: 18, paddingBottom: 44, width: '100%', maxWidth: 640, alignSelf: 'center' },
  title: { fontSize: 28, fontFamily: 'Sora', fontWeight: '700', color: c.text },
  subtitle: { fontFamily: 'Sora', fontSize: p.largerText ? 21 : 17, fontWeight: '600', color: c.text },
  copy: { fontFamily: 'Sora', color: c.muted, fontSize: p.largerText ? 18 : 15, lineHeight: p.largerText ? 29 : 23 },
  card: { padding: 18, gap: 10, borderRadius: 18, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface, boxShadow: c.quietShadow },
  input: { borderWidth: 1, borderColor: c.border, borderRadius: 12, padding: 14, color: c.text, backgroundColor: c.elevated, fontFamily: 'Sora', fontSize: p.largerText ? 20 : 16 },
  button: { padding: 14, minHeight: 48, borderRadius: 12, alignItems: 'center', borderWidth: 1, borderColor: c.border, backgroundColor: c.surface, boxShadow: c.quietShadow },
  buttonText: { fontFamily: 'Sora', color: c.text, fontWeight: '600', fontSize: p.largerText ? 18 : 14 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  error: { color: c.danger, lineHeight: 22 },
});

}

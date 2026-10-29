import { Pressable, StyleSheet, Text, TextInput, type TextInputProps } from 'react-native';
export function Action({ title, onPress, disabled = false }: { title: string; onPress: () => void; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[ui.button, disabled && { opacity: 0.45 }]}><Text style={ui.buttonText}>{title}</Text></Pressable>;
}
export function Field(props: TextInputProps) {
  return <TextInput placeholderTextColor="#74847A" {...props} accessibilityLabel={props.accessibilityLabel || props.placeholder} style={[ui.input, props.style]} />;
}
export const ui = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F5F7F2' },
  content: { padding: 22, gap: 14, paddingBottom: 44 },
  title: { fontSize: 28, fontWeight: '700', color: '#142820' },
  subtitle: { fontSize: 17, fontWeight: '600', color: '#245B45' },
  copy: { color: '#40574A', fontSize: 15, lineHeight: 23 },
  card: { padding: 18, gap: 10, borderRadius: 18, backgroundColor: '#FFFFFF' },
  input: { borderWidth: 1, borderColor: '#CAD7CE', borderRadius: 12, padding: 14, color: '#142820', backgroundColor: '#FFFFFF', fontSize: 16 },
  button: { padding: 14, borderRadius: 12, alignItems: 'center', backgroundColor: '#245B45' },
  buttonText: { color: 'white', fontWeight: '600', fontSize: 15 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  error: { color: '#A32C24', lineHeight: 22 },
});

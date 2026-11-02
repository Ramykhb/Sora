import { View } from 'react-native';
import { useState } from 'react';
import { usePreferences, type Preferences } from '@/providers/preferences';
import { speech } from '@/lib/speech';
import { Card, Icon, Label, Tap, Toggle, type IconName } from './sora-ui';
const rows: { key: keyof Pick<Preferences, 'speak' | 'guidance' | 'vibration' | 'largerText' | 'highContrast'>; title: string; detail: string; icon: IconName }[] = [
  { key: 'speak', title: 'Speak descriptions', detail: 'Read results out loud', icon: 'volume-high-outline' },
  { key: 'guidance', title: 'Voice guidance', detail: 'Give step-by-step prompts', icon: 'pulse-outline' },
  { key: 'vibration', title: 'Vibration feedback', detail: 'Confirm key actions', icon: 'phone-portrait-outline' },
  { key: 'largerText', title: 'Larger text', detail: 'Increase text size in the app', icon: 'text-outline' },
];
export function PreferenceControls() {
  const { preferences, colors, update, storageError } = usePreferences();
  const [contrastExpanded, setContrastExpanded] = useState(false);
  return <View style={{ gap: 10 }}>
    {rows.map(row => <Card key={row.key} style={{ padding: 14, minHeight: 78, flexDirection: 'row', alignItems: 'center', gap: 14 }}><Icon name={row.icon} color={row.key === 'guidance' ? colors.accent : colors.text} size={26} /><View style={{ flex: 1, gap: 3 }}><Label bold size={14}>{row.title}</Label><Label muted size={11}>{row.detail}</Label></View><Toggle label={row.title} value={preferences[row.key]} onChange={value => { update({ [row.key]: value }); if (row.key === 'speak' && !value) void speech.stop(); }} /></Card>)}
    <Tap label="High contrast settings" expanded={contrastExpanded} onPress={() => setContrastExpanded(value => !value)}><Card tone="accent" style={{ padding: 14, minHeight: 94, flexDirection: 'row', alignItems: 'center', gap: 14 }}><Icon name="contrast-outline" size={26} color={colors.text} /><View style={{ flex: 1, gap: 3 }}><Label bold size={14}>High contrast</Label><Label muted size={11}>Use stronger colors for better visibility</Label></View><Icon name={contrastExpanded ? 'chevron-down' : 'chevron-forward'} size={21} color={colors.muted} /></Card></Tap>
    {contrastExpanded && <Card style={{ flexDirection: 'row', alignItems: 'center' }}><Label style={{ flex: 1 }}>Enable high contrast</Label><Toggle label="High contrast" value={preferences.highContrast} onChange={highContrast => update({ highContrast })} /></Card>}
    <Label muted bold size={11} style={{ marginTop: 18, letterSpacing: 1.4 }}>APPEARANCE</Label>
    <View style={{ flexDirection: 'row', borderRadius: 18, backgroundColor: colors.elevated, padding: 5, borderWidth: 1, borderColor: colors.border }}>{(['system', 'light', 'dark'] as const).map(theme => <Tap key={theme} label={`${theme} appearance`} selected={preferences.theme === theme} onPress={() => update({ theme })} style={{ flex: 1, backgroundColor: preferences.theme === theme ? colors.primary : 'transparent', borderRadius: 13, alignItems: 'center', justifyContent: 'center', ...(preferences.theme === theme ? { boxShadow: colors.quietShadow } : {}) }}><Label size={12} bold style={{ color: preferences.theme === theme ? '#FFFFFF' : colors.muted }}>{theme[0].toUpperCase() + theme.slice(1)}</Label></Tap>)}</View>
    {!!storageError && <Label accessibilityRole="alert" style={{ color: colors.danger }}>{storageError}</Label>}
  </View>;
}

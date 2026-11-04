import { View } from 'react-native';
import { useState } from 'react';
import { usePreferences, type Preferences } from '@/providers/preferences';
import { useVoiceCommands } from '@/providers/voice-commands';
import { speech } from '@/lib/speech';
import { Card, Icon, Label, Tap, Toggle, type IconName } from './sora-ui';
const rows: { key: keyof Pick<Preferences, 'speak' | 'guidance' | 'vibration' | 'largerText' | 'highContrast'>; title: string; detail: string; icon: IconName }[] = [
  { key: 'speak', title: 'Speak descriptions', detail: 'Read results out loud', icon: 'volume-high-outline' },
  { key: 'guidance', title: 'Voice guidance', detail: 'Give step-by-step prompts', icon: 'pulse-outline' },
  { key: 'vibration', title: 'Vibration feedback', detail: 'Confirm key actions', icon: 'phone-portrait-outline' },
  { key: 'largerText', title: 'Larger text', detail: 'Increase text size in the app', icon: 'text-outline' },
  { key: 'highContrast', title: 'High contrast', detail: 'Use stronger colors for visibility', icon: 'contrast-outline' },
];
export function PreferenceControls() {
  const { preferences, colors, update, storageError } = usePreferences();
  const voice = useVoiceCommands();
  const [voiceExpanded, setVoiceExpanded] = useState(false);
  return <View style={{ gap: 10 }}>
    {rows.map(row => <Card key={row.key} tone={row.key === 'highContrast' ? 'accent' : 'default'} style={{ padding: 14, minHeight: 76, flexDirection: 'row', alignItems: 'center', gap: 14 }}><Icon name={row.icon} color={colors.primary} size={25} /><View style={{ flex: 1, gap: 3 }}><Label bold size={14}>{row.title}</Label><Label muted size={11}>{row.detail}</Label></View><Toggle label={row.title} value={preferences[row.key]} onChange={value => { update({ [row.key]: value }); if (row.key === 'speak' && !value) void speech.stop(); }} /></Card>)}
    <Label muted bold size={11} style={{ marginTop: 18, letterSpacing: 1.4 }}>APPEARANCE</Label>
    <View style={{ flexDirection: 'row', borderRadius: 18, backgroundColor: colors.elevated, padding: 5, borderWidth: 1, borderColor: colors.border }}>{(['system', 'light', 'dark'] as const).map(theme => <Tap key={theme} label={`${theme} appearance`} selected={preferences.theme === theme} onPress={() => update({ theme })} style={{ flex: 1, backgroundColor: preferences.theme === theme ? colors.primary : 'transparent', borderRadius: 13, alignItems: 'center', justifyContent: 'center', ...(preferences.theme === theme ? { boxShadow: colors.quietShadow } : {}) }}><Label size={12} bold style={{ color: preferences.theme === theme ? colors.onPrimary : colors.muted }}>{theme[0].toUpperCase() + theme.slice(1)}</Label></Tap>)}</View>
    <Tap label="Hands-free voice controls" expanded={voiceExpanded} onPress={() => setVoiceExpanded(value => !value)}><Card tone="quiet" style={{ padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12 }}><Icon name="mic-outline" size={22} /><View style={{ flex: 1 }}><Label bold size={13}>Hands-free voice controls</Label><Label muted size={11}>Listening and spoken questions</Label></View><Icon name={voiceExpanded ? 'chevron-down' : 'chevron-forward'} size={20} color={colors.muted} /></Card></Tap>
    {voiceExpanded && <>
      <Card style={{ gap: 10 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}><Icon name="mic-outline" /><View style={{ flex: 1 }}><Label bold>Hands-free voice</Label><Label muted size={12}>Ask questions while SORA is open. Start app commands with “Hey Sora”. “Hey Sora, start stream” consents to camera processing and starts live assistance.</Label></View><Toggle label="Hands-free voice" value={preferences.voiceCommands} onChange={voiceCommands => { update({ voiceCommands }); voice.retry(); }} /></View><Label accessibilityLiveRegion="polite" muted size={12}>{voice.status}</Label><Label muted size={11}>Your phone’s speech service processes your speech and may require internet access.</Label>{preferences.voiceCommands && <Tap label="Retry voice listening" onPress={voice.retry}><Label bold size={13}>Retry voice listening</Label></Tap>}</Card>
      <Card style={{ gap: 10 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}><View style={{ flex: 1 }}><Label bold>Hands-free questions</Label><Label muted size={12}>Turn off to chat freely. Hey Sora commands remain available. Say “Hey Sora, stop listening” or “Hey Sora, start listening”. Paused streams ignore ordinary speech automatically.</Label></View><Toggle label="Hands-free questions" value={preferences.handsFreeQuestions} onChange={voice.setQuestionListening} /></View></Card>
    </>}
    {!!storageError && <Label accessibilityRole="alert" style={{ color: colors.danger }}>{storageError}</Label>}
  </View>;
}

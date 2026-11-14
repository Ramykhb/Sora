import { useSyncExternalStore } from 'react';
import { View } from 'react-native';
import { parseWalkingRoute } from '@/lib/speech-policy';
import { speech } from '@/lib/speech';
import { usePreferences } from '@/providers/preferences';
import { Action, useUI } from './controls';
import { Label } from './sora-ui';

// The same route cursor drives voice commands and both answer surfaces.
export function RouteAnswer({ text, language, color, onError }: { text: string; language: string; color?: string; onError?: (message: string) => void }) {
  const playback = useSyncExternalStore(speech.subscribeRoute, speech.getRoutePlayback, speech.getRoutePlayback);
  const route = parseWalkingRoute(text);
  const ui = useUI();
  const { colors } = usePreferences();
  if (!route) return <Label size={14} selectable style={color ? { color } : undefined}>{text}</Label>;
  const current = playback?.text === text && playback.language === language ? playback : null;
  const index = current?.index ?? 0;
  const full = current?.full ?? false;
  const lang = language.split(/[-_]/)[0];
  const labels = lang === 'fr'
    ? { previous: 'Étape précédente', next: 'Étape suivante', full: 'Afficher tout l’itinéraire', progress: `Étape ${index + 1} sur ${route.steps.length}` }
    : lang === 'ar'
      ? { previous: 'الخطوة السابقة', next: 'الخطوة التالية', full: 'اعرض المسار كاملاً', progress: `الخطوة ${index + 1} من ${route.steps.length}` }
      : { previous: 'Previous step', next: 'Next step', full: 'Show full route', progress: `Step ${index + 1} of ${route.steps.length}` };
  function control(action: 'previous' | 'next' | 'full') {
    speech.rememberAnswer(text, language);
    void (action === 'full' ? speech.showFullRoute() : speech.moveRouteStep(action === 'next' ? 1 : -1))
      .catch(error => onError?.(error instanceof Error ? error.message : 'Unable to play the route.'));
  }
  return <View style={{ gap: 10 }}>
    <Label bold size={14} selectable style={color ? { color } : undefined}>{route.intro}</Label>
    <Label size={12} style={color ? { color } : undefined}>{labels.progress}</Label>
    <View accessibilityLiveRegion="polite" style={{ gap: 8 }}>
      {(full ? route.steps : [route.steps[index]]).map(step => <Label key={step} size={14} bold={step === route.steps[index]} selectable style={{ color: color ?? colors.text }}>{step}</Label>)}
    </View>
    <View style={ui.row}>
      <Action title={labels.previous} disabled={index === 0} onPress={() => control('previous')} />
      <Action title={labels.next} disabled={index === route.steps.length - 1} onPress={() => control('next')} />
      <Action title={labels.full} onPress={() => control('full')} />
    </View>
    {!!route.notes && <Label size={12} selectable style={color ? { color } : undefined}>{route.notes}</Label>}
  </View>;
}

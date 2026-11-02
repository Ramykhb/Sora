import { usePreferences } from '@/providers/preferences';
export function useTheme() {
  const { colors } = usePreferences();
  return { text: colors.text, background: colors.background, backgroundElement: colors.surface, backgroundSelected: colors.elevated, textSecondary: colors.muted };
}

import { createContext, useCallback, useContext } from 'react';
import { useFocusEffect } from 'expo-router';

export const TabBarContext = createContext({ native: false, setFullscreen: (_hidden: boolean) => {} });
export function useNativeTabBar() { return useContext(TabBarContext).native; }
/** Camera capture owns the whole screen; restore the tabs when it loses focus. */
export function useFullscreenTabBar(hidden: boolean) {
  const { setFullscreen } = useContext(TabBarContext);
  useFocusEffect(useCallback(() => {
    setFullscreen(hidden);
    return () => setFullscreen(false);
  }, [hidden, setFullscreen]));
}

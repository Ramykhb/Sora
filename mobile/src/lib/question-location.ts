export async function questionLocation(question: string) {
  if (!/\b(closest|closes|nearest|nearby|near me|how far|plus proche|près de moi)\b|أقرب|اقرب|بالقرب|كم يبعد/i.test(question)) return undefined;
  try {
    const Location = await import('expo-location');
    const permission = await Location.requestForegroundPermissionsAsync();
    if (!permission.granted) return undefined;
    // A bounded, fresh fix; never reuse an old location for a distance answer.
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const position = await Promise.race([
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
        new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Location timed out')), 10000); }),
      ]);
      return { latitude: position.coords.latitude, longitude: position.coords.longitude };
    } finally { clearTimeout(timer); }
  } catch { return undefined; }
}

export async function currentLocation(highAccuracy = false) {
  const Location = await import('expo-location');
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) throw new Error('Allow location access in Settings to share your SOS location.');
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const position = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: highAccuracy ? Location.Accuracy.High : Location.Accuracy.Balanced }),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Location timed out. Move where GPS is available and try again.')), 15000); }),
    ]);
    return {
      latitude: position.coords.latitude, longitude: position.coords.longitude,
      captured_at: new Date(position.timestamp).toISOString(), accuracy_meters: position.coords.accuracy,
    };
  } finally { clearTimeout(timer); }
}

export async function questionLocation(question: string) {
  if (!/\b(closest|closes|nearest|nearby|near me|how far|plus proche|près de moi)\b|أقرب|اقرب|بالقرب|كم يبعد/i.test(question)) return undefined;
  try {
    const { latitude, longitude } = await currentLocation();
    return { latitude, longitude };
  } catch { return undefined; }
}

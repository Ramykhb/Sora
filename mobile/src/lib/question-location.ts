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

export function isTripQuestion(question: string) {
  if (/^\s*(?:please\s+)?(?:(?:(?:route|directions?)\s+(?:to\s+)?|(?:take|guide|direct)\s+me\s+(?:to\s+)?|navigate\s+(?:me\s+)?(?:to\s+)?|(?:start|begin)\s+(?:a\s+)?(?:trip|route)\s+to\s+|how\s+(?:do|can)\s+i\s+get\s+(?:to\s+)?|(?:let['’]s\s+)?go\s+(?:to\s+)?)(?:there|it|that(?:\s+(?:place|restaurant|one))?|this\s+place|the\s+(?:place|restaurant))|(?:itin[ée]raire\s+vers|emm[èe]ne[- ]moi)\s+(?:l[àa](?:-bas)?|cet\s+endroit)|(?:خذني\s+(?:إلى\s+)?|(?:مسار|اتجاهات)\s+إلى\s+)(?:هناك|ذلك المكان))(?:\s+please)?\s*[.!?؟]*\s*$/i.test(question)) return true;
  return /\b(?:directions?|route|trip)\s+(?:to|towards?|for)\b|\b(?:start|begin|plan)\s+(?:(?:a|my|the)\s+)?(?:walking\s+)?(?:trip|route)\b|\b(?:navigate|guide|take|direct)\s+me\s+to\b|\bnavigate\s+to\b|\bhow\s+(?:do|can)\s+i\s+get\s+to\b|\b(?:itin[ée]raire|trajet|directions?)\s+(?:vers|pour)\b|(?:ابدأ|ابدا).*(?:رحلة|مسار)|(?:اتجاهات|مسار|طريق)\s+إلى|خذني\s+إلى/i.test(question);
}

export async function questionLocation(question: string) {
  const trip = isTripQuestion(question);
  if (!trip && !/\b(closest|closes|nearest|nearby|near me|how far|plus proche|près de moi)\b|أقرب|اقرب|بالقرب|كم يبعد/i.test(question)) return undefined;
  try {
    const { latitude, longitude } = await currentLocation(trip);
    return { latitude, longitude };
  } catch { return undefined; }
}

export async function questionLocation(question) {
  if (!/\b(closest|closes|nearest|nearby|near me|how far|plus proche|près de moi)\b|أقرب|اقرب|بالقرب|كم يبعد/i.test(question) || !globalThis.navigator?.geolocation) return undefined;
  return new Promise(resolve => navigator.geolocation.getCurrentPosition(
    ({ coords }) => resolve({ latitude: coords.latitude, longitude: coords.longitude }),
    () => resolve(undefined),
    { enableHighAccuracy: false, maximumAge: 0, timeout: 10000 },
  ));
}

export function destinationInput(nickname: string, latitude: string, longitude: string) {
  const name = nickname.normalize('NFKC').trim().replace(/\s+/g, ' ');
  if (!name || name.length > 80 || !/[\p{L}\p{N}]/u.test(name)) {
    throw new Error('Enter a nickname of 1–80 characters containing letters or numbers.');
  }
  function coordinate(text: string, label: string, limit: number) {
    const value = text.trim();
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value) || !Number.isFinite(Number(value)) || Math.abs(Number(value)) > limit) {
      throw new Error(`${label} must be a decimal number between -${limit} and ${limit}.`);
    }
    return Number(value);
  }
  return { nickname: name, latitude: coordinate(latitude, 'Latitude', 90), longitude: coordinate(longitude, 'Longitude', 180) };
}

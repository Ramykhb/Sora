export function serverOrigin(value: string) {
  let url: URL;
  try { url = new URL(value.trim()); }
  catch { throw new Error('Enter a server address such as http://192.168.1.10:8000'); }
  if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) {
    throw new Error('Use an HTTP or HTTPS server address without a username or password.');
  }
  if (url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Enter only the server origin, without /api/v1 or another path.');
  }
  return url.origin;
}

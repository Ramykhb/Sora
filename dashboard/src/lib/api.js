export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
export async function responseError(response) {
  const body = await response.json().catch(() => ({}));
  const message = body.error?.message || (typeof body.detail === 'string' ? body.detail : body.detail?.map(item => item.msg).join('\n')) || `Request failed (${response.status})`;
  return new ApiError(response.status, message);
}

export class ApiClient {
  tokens = null;
  expiresAt = 0;
  refreshing = null;
  constructor(baseUrl, onTokens = () => {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.onTokens = onTokens;
  }
  url(path) { return `${this.baseUrl}/api/v1${path}`; }
  socketUrl(path) { return new URL(this.url(path), globalThis.location?.origin).href.replace(/^http/, 'ws'); }
  setTokens(tokens) {
    this.onTokens(tokens);
    this.tokens = tokens;
    this.expiresAt = tokens ? Date.now() + tokens.expires_in * 1000 : 0;
  }
  async fetch(path, init = {}, timeoutMs = 120000) {
    if (timeoutMs === 0) return fetch(this.url(path), init);
    const controller = new AbortController();
    const abort = () => controller.abort();
    init.signal?.addEventListener('abort', abort, { once: true });
    if (init.signal?.aborted) controller.abort();
    const timer = timeoutMs ? setTimeout(abort, timeoutMs) : undefined;
    try { return await fetch(this.url(path), { ...init, signal: controller.signal }); }
    catch (error) {
      if (controller.signal.aborted && !init.signal?.aborted) throw new ApiError(408, 'The server took too long. Please retry.');
      throw error;
    } finally { clearTimeout(timer); init.signal?.removeEventListener('abort', abort); }
  }
  async publicRequest(path, body) {
    const response = await this.fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, 30000);
    if (!response.ok) throw await responseError(response);
    return response.status === 204 ? null : response.json();
  }
  async restore(refreshToken) {
    this.tokens = { refresh_token: refreshToken };
    return this.refresh();
  }
  async refresh() {
    if (this.refreshing) return this.refreshing;
    const previous = this.tokens;
    this.refreshing = (async () => {
      if (!previous) throw new ApiError(401, 'Please sign in.');
      try {
        const tokens = await this.publicRequest('/auth/refresh', { refresh_token: previous.refresh_token });
        if (this.tokens !== previous) throw new ApiError(401, 'Sign-in changed. Please retry.');
        this.setTokens(tokens);
        return tokens.access_token;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && this.tokens === previous) this.setTokens(null);
        throw error;
      }
    })().finally(() => { this.refreshing = null; });
    return this.refreshing;
  }
  async token() {
    if (!this.tokens) throw new ApiError(401, 'Please sign in.');
    return Date.now() >= this.expiresAt - 30000 ? this.refresh() : this.tokens.access_token;
  }
  async response(path, init = {}, timeoutMs = 120000) {
    const token = await this.token();
    const send = value => this.fetch(path, { ...init, headers: { ...init.headers, Authorization: `Bearer ${value}` } }, timeoutMs);
    let response = await send(token);
    if (response.status === 401) {
      const next = this.tokens && this.tokens.access_token !== token ? this.tokens.access_token : await this.refresh();
      response = await send(next);
      if (response.status === 401) this.setTokens(null);
    }
    if (!response.ok) throw await responseError(response);
    return response;
  }
  async request(path, method = 'GET', body, signal) {
    const response = await this.response(path, { method, signal, ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
    return response.status === 204 ? null : response.json();
  }
  async readiness() {
    const send = async () => fetch(`${this.baseUrl}/ready`, { headers: { Authorization: `Bearer ${await this.token()}` } });
    let response = await send();
    if (response.status === 401) { await this.refresh(); response = await send(); }
    if (response.status === 503) return response.json();
    if (!response.ok) throw await responseError(response);
    return response.json();
  }
  async upload(path, data) { return (await this.response(path, { method: 'POST', body: data })).json(); }
}

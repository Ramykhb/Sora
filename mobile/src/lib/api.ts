export type Language = 'en' | 'fr' | 'ar';
export type Scope = 'auto' | 'recent' | 'memory';
export type User = { id: string; email: string; display_name: string; email_verified: boolean; role: string };
export type Tokens = { access_token: string; refresh_token: string; expires_in: number; user: User };
export type CaptureSession = { id: string; status: string; language: Language; alerts_enabled: boolean; created_at: string; expires_at: string };
export type Frame = { id: string; session_id: string; caption: string; ocr_text: string; captured_at: string; enrichment_status?: 'pending' | 'complete' | 'failed'; enrichment_ms?: number | null; processing_warnings: string[]; detected_objects: { label: string; confidence: number }[] };
export type Answer = { id: string; session_id: string; question: string; answer: string; language: Language; uncertain: boolean; evidence_frame_ids: string[]; processing_warnings: string[]; created_at: string };
export type LiveEvent = { type: string; message?: string; code?: string; reason?: string; language?: Language; frame?: Frame; question?: Answer; session?: CaptureSession };
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function errorFrom(response: Response) {
  const body = await response.json().catch(() => ({}));
  const message = body.error?.message ?? (typeof body.detail === 'string' ? body.detail : body.detail?.map((d: { msg: string }) => d.msg).join('\n')) ?? `Request failed (${response.status})`;
  return new ApiError(response.status, message);
}

async function fetchBounded(url: string, init: RequestInit, timeoutMs = 120000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try { return await fetch(url, { ...init, signal: controller.signal }); }
  catch (error) {
    if (controller.signal.aborted) throw new ApiError(408, 'The server took too long. Try again.');
    throw error;
  } finally { clearTimeout(timeout); }
}

// Kept separate from device APIs so refresh/retry behavior can be tested with a fake server.
export class ApiClient {
  tokens: Tokens | null = null;
  private expiresAt = 0;
  private refreshing: Promise<string> | null = null;
  constructor(public baseUrl: string, private onTokens: (tokens: Tokens | null) => Promise<void>) {}
  url(path: string) { return `${this.baseUrl}/api/v1${path}`; }
  async setTokens(tokens: Tokens | null) {
    await this.onTokens(tokens);
    this.tokens = tokens;
    this.expiresAt = tokens ? Date.now() + tokens.expires_in * 1000 : 0;
  }
  async publicRequest<T>(path: string, body: unknown): Promise<T> {
    const response = await fetchBounded(this.url(path), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, 30000);
    if (!response.ok) throw await errorFrom(response);
    return response.status === 204 ? undefined as T : response.json();
  }
  async restore(refreshToken: string) {
    this.tokens = { refresh_token: refreshToken } as Tokens;
    this.expiresAt = 0;
    return this.refresh();
  }
  async refresh(): Promise<string> {
    if (this.refreshing) return this.refreshing;
    const previous = this.tokens;
    this.refreshing = (async () => {
      if (!previous) throw new ApiError(401, 'Please sign in.');
      try {
        const tokens = await this.publicRequest<Tokens>('/auth/refresh', { refresh_token: previous.refresh_token });
        if (this.tokens !== previous) throw new ApiError(401, 'Sign-in changed. Please retry.');
        await this.setTokens(tokens);
        return tokens.access_token;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && this.tokens === previous) await this.setTokens(null);
        throw error;
      }
    })().finally(() => { this.refreshing = null; });
    return this.refreshing;
  }
  async token() {
    if (!this.tokens) throw new ApiError(401, 'Please sign in.');
    return Date.now() >= this.expiresAt - 30000 ? this.refresh() : this.tokens.access_token;
  }
  async response(path: string, init: RequestInit = {}) {
    const token = await this.token();
    const send = (value: string) => fetchBounded(this.url(path), { ...init, headers: { ...init.headers, Authorization: `Bearer ${value}` } });
    let response = await send(token);
    if (response.status === 401) {
      const next = this.tokens?.access_token !== token && this.tokens ? this.tokens.access_token : await this.refresh();
      response = await send(next);
      if (response.status === 401) await this.setTokens(null);
    }
    if (!response.ok) throw await errorFrom(response);
    return response;
  }
  async request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const response = await this.response(path, { method, ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
    return response.status === 204 ? undefined as T : response.json();
  }
  async upload<T>(path: string, form: FormData): Promise<T> {
    return (await this.response(path, { method: 'POST', body: form })).json();
  }
}

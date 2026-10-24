function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export class LocalApiError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

export class LocalApiClient {
  constructor(private readonly timeoutMs = 8_000) {}
  private session: { token: string; expires: number } | null = null;

  private async exchange(path: string, options: RequestInit): Promise<{ ok: boolean; status: number; value: unknown }> {
    const controller = new AbortController();
    const abort = () => controller.abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    if (options.signal?.aborted) controller.abort();
    let timedOut = false;
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal });
      let value: unknown = null;
      if (response.ok) {
        try { value = await response.json(); }
        catch { throw new Error('Unexpected local API response.'); }
      }
      return { ok: response.ok, status: response.status, value };
    } catch (cause) {
      if (timedOut) throw new Error('Request timed out. Reload data before retrying.');
      if (cause instanceof Error && cause.message === 'Unexpected local API response.') throw cause;
      throw new Error('Cannot reach the local backend. Reload data before retrying.');
    } finally {
      window.clearTimeout(timeout);
      options.signal?.removeEventListener('abort', abort);
    }
  }

  private async token(): Promise<string> {
    if (this.session && this.session.expires > Date.now()) return this.session.token;
    const response = await this.exchange('/api/session', { cache: 'no-store', headers: { 'X-PCC-Client': 'web' } });
    if (!response.ok) throw new Error('Cannot establish a local session. Reload and retry.');
    const value = response.value;
    if (!record(value) || typeof value.token !== 'string' || value.token.length < 32
      || !Number.isInteger(value.expires_in_seconds) || Number(value.expires_in_seconds) < 1 || Number(value.expires_in_seconds) > 1800) {
      throw new Error('Unexpected local session response.');
    }
    this.session = { token: value.token, expires: Date.now() + (Number(value.expires_in_seconds) - 1) * 1000 };
    return value.token;
  }

  async request(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<unknown> {
    for (let attempt = 0; attempt < 2; attempt++) {
      const headers: Record<string, string> = { 'X-PCC-Client': 'web' };
      if (method !== 'GET') {
        try { headers['X-PCC-Session'] = await this.token(); }
        catch { throw new Error('Cannot establish a local session. Reload and retry.'); }
        headers['Content-Type'] = 'application/json';
      }
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
      const response = await this.exchange(path, { method, headers, cache: 'no-store', signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      // A 401 is rejected before mutation by the server; network errors are never replayed.
      if (method !== 'GET' && response.status === 401 && attempt === 0) {
        this.session = null;
        continue;
      }
      if (!response.ok) {
        if (response.status === 409) throw new LocalApiError(409, 'Data changed or is busy. Reload before retrying.');
        if (response.status === 422) throw new LocalApiError(422, 'Check the profile name and desired settings.');
        if (response.status === 503) throw new LocalApiError(503, 'Local storage is unavailable. Existing data has been kept.');
        throw new LocalApiError(response.status, `Local request failed (HTTP ${response.status}).`);
      }
      return response.value;
    }
    throw new Error('Cannot establish a local session. Reload and retry.');
  }
}

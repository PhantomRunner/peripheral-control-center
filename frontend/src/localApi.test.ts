import { describe, expect, it, vi } from 'vitest';
import { LocalApiClient } from './localApi';
import { pendingRequest } from './test/fixtures';

const session = () => Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 });

describe('local mutation client', () => {
  it('bootstraps a local session and sends JSON with a custom session header', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(session()).mockResolvedValueOnce(Response.json({ saved: true }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await new LocalApiClient().request('/api/profiles', 'POST', { name: 'Work' })).toEqual({ saved: true });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/session');
    const [path, options] = fetchMock.mock.calls[1];
    expect(path).toBe('/api/profiles');
    expect(options.headers).toEqual({ 'X-PCC-Client': 'web', 'X-PCC-Session': 'a'.repeat(43), 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual({ name: 'Work' });
  });

  it('refreshes a rejected session once, before the server has mutated anything', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(session()).mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockResolvedValueOnce(session()).mockResolvedValueOnce(Response.json({ saved: true }));
    vi.stubGlobal('fetch', fetchMock);
    await new LocalApiClient().request('/api/profiles', 'POST', {});
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(['/api/session', '/api/profiles', '/api/session', '/api/profiles']);
  });

  it('does not replay a mutation after a network failure', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(session()).mockRejectedValueOnce(new Error('/private/path'));
    vi.stubGlobal('fetch', fetchMock);
    await expect(new LocalApiClient().request('/api/profiles', 'POST', {})).rejects.toThrow('Reload data before retrying.');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not send a mutation if session bootstrap fails', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ token: 'invalid' }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(new LocalApiClient().request('/api/profiles', 'POST', {})).rejects.toThrow('Cannot establish a local session.');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('reports conflicts without leaking response diagnostics', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(session()).mockResolvedValueOnce(new Response('/private/path', { status: 409 })));
    await expect(new LocalApiClient().request('/api/profiles', 'PUT', {})).rejects.toThrow('Data changed or is busy. Reload before retrying.');
  });

  it('times out a stalled mutation without replaying it', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValueOnce(session()).mockImplementationOnce(pendingRequest);
    vi.stubGlobal('fetch', fetchMock);
    const request = new LocalApiClient().request('/api/profiles', 'POST', {});
    const assertion = expect(request).rejects.toThrow('Request timed out. Reload data before retrying.');
    await vi.advanceTimersByTimeAsync(8_000);
    await assertion;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

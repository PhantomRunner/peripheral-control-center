import { describe, expect, it, vi } from 'vitest';
import { fetchDevices } from './api';
import { deviceResponse, keyboard, mouse } from './test/fixtures';

describe('device API', () => {
  it('uses the same-origin read-only endpoint and preserves unknown readings', async () => {
    const fetchMock = vi.fn().mockResolvedValue(deviceResponse());
    vi.stubGlobal('fetch', fetchMock);
    const signal = new AbortController().signal;
    expect(await fetchDevices(signal)).toEqual([mouse, keyboard]);
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith('/api/devices', { cache: 'no-store', signal });
  });

  it('accepts an empty adapter list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(deviceResponse([])));
    expect(await fetchDevices(new AbortController().signal)).toEqual([]);
  });

  it('reports HTTP failures without exposing the server response body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private diagnostics', { status: 503 })));
    await expect(fetchDevices(new AbortController().signal)).rejects.toThrow('Backend returned HTTP 503.');
  });

  it('does not expose raw transport errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('/private/machine/USB-serial')));
    await expect(fetchDevices(new AbortController().signal)).rejects.toThrow('Cannot reach the local backend.');
  });

  it('rejects invalid JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Proxy error</html>')));
    await expect(fetchDevices(new AbortController().signal)).rejects.toThrow('Unexpected API response.');
  });

  it.each([
    null,
    { devices: {} },
    { devices: [null] },
    { devices: [{ id: 'incomplete' }] },
    { devices: [mouse, mouse] },
    { devices: [{ ...mouse, status: ['offline'] }] },
    { devices: [{ ...mouse, battery_percent: 'unknown' }] },
    { devices: [{ ...mouse, connected_usb_ids: ['/private/device/path'] }] },
    { devices: [{ ...mouse, firmware_version: undefined }] },
    { devices: [{ ...mouse, capabilities: { usb_discovery: true } }] },
    { devices: [{ ...mouse, connection: { ...mouse.connection, wireless_link_verified: 'unknown' } }] },
  ])('rejects a malformed device response (%#)', async (payload) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(payload)));
    await expect(fetchDevices(new AbortController().signal)).rejects.toThrow('Unexpected API response.');
  });
});

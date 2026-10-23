import { describe, expect, it, vi } from 'vitest';
import { SettingsClient } from './settingsApi';

describe('polling Apply readback', () => {
  it.each([125, 250, 500, 1000, 2000, 4000, 8000])('requires matching %i Hz readback', async (rate) => {
    const desired = { kind: 'mouse' as const, dpi: null, polling_rate_hz: rate };
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: 'pulsar_susanto_x', status: 'verified', settings: desired }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await new SettingsClient().apply('pulsar_susanto_x', desired)).toEqual(desired);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ settings: desired });
  });

  it('rejects unknown or incorrect polling in a nominally successful response', async () => {
    const desired = { kind: 'mouse' as const, dpi: null, polling_rate_hz: 8000 };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: 'pulsar_susanto_x', status: 'verified', settings: { ...desired, polling_rate_hz: 1000 } })));
    await expect(new SettingsClient().apply('pulsar_susanto_x', desired)).rejects.toThrow('Readback differs');
  });
});

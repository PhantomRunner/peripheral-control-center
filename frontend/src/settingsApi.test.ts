import { describe, expect, it, vi } from 'vitest';
import { SettingsClient } from './settingsApi';

describe('polling Apply readback', () => {
  it.each([125, 250, 500, 1000, 2000, 4000, 8000])('requires matching %i Hz readback', async (rate) => {
    const desired = { kind: 'mouse' as const, dpi: null, polling_rate_hz: rate };
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: 'pulsar_susanto_x', status: 'verified', settings: desired }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await new SettingsClient().apply('pulsar_susanto_x', desired)).toEqual(desired);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ settings: desired, vendor_tools_closed: false, allow_device_memory_writes: false });
  });

  it('rejects unknown or incorrect polling in a nominally successful response', async () => {
    const desired = { kind: 'mouse' as const, dpi: null, polling_rate_hz: 8000 };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: 'pulsar_susanto_x', status: 'verified', settings: { ...desired, polling_rate_hz: 1000 } })));
    await expect(new SettingsClient().apply('pulsar_susanto_x', desired)).rejects.toThrow('Readback differs');
  });
});

describe('RGB Apply readback', () => {
  it('compares RGB values semantically, ignoring color case and property order', async () => {
    const desired = { kind: 'keyboard' as const, rgb: { mode: 'static' as const, color: '#AABBCC', brightness_percent: 60 } };
    const actual = { kind: 'keyboard', rgb: { brightness_percent: 60, color: '#aabbcc', mode: 'static' } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: 'ajazz_ak820_pro', status: 'verified', settings: actual })));
    expect(await new SettingsClient().apply('ajazz_ak820_pro', desired)).toEqual(actual);
  });

  it('does not treat an acknowledgement as settings readback', async () => {
    const desired = { kind: 'keyboard' as const, rgb: { mode: 'static' as const, color: '#112233', brightness_percent: 60 } };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: 'ajazz_ak820_pro', status: 'acknowledged', command: 0x13 })));
    await expect(new SettingsClient().apply('ajazz_ak820_pro', desired)).rejects.toThrow('No matching RGB acknowledgement');
  });
});

const requestedRgb = { kind: 'keyboard' as const, rgb: { mode: 'static' as const, color: '#4080ff', brightness_percent: 60 } };
const ackResult = { device_id: 'ajazz_ak820_pro', status: 'acknowledged', requested_settings: requestedRgb,
  actual_settings: null, feedback: 'command_acknowledgements', readback_available: false, persistence_verified: false, may_persist: true };

it('keeps acknowledged RGB intent separate from actual settings', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
    .mockResolvedValueOnce(Response.json(ackResult));
  vi.stubGlobal('fetch', fetchMock);
  expect(await new SettingsClient().apply('ajazz_ak820_pro', requestedRgb, true, true)).toEqual({ status: 'acknowledged', requested: requestedRgb, actual: null });
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ settings: requestedRgb, vendor_tools_closed: true, allow_device_memory_writes: true });
});

it.each([
  { ...ackResult, actual_settings: requestedRgb }, { ...ackResult, persistence_verified: true },
  { ...ackResult, feedback: 'usb_write_only' },
  { ...ackResult, requested_settings: { ...requestedRgb, rgb: { ...requestedRgb.rgb, color: '#ffffff' } } },
])('rejects invented or unmatched RGB acknowledgements (%#)', async (response) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
    .mockResolvedValueOnce(Response.json(response)));
  await expect(new SettingsClient().apply('ajazz_ak820_pro', requestedRgb, true, true)).rejects.toThrow('No matching RGB acknowledgement');
});

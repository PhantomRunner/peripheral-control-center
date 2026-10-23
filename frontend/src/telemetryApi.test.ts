import { expect, it, vi } from 'vitest';
import { TelemetryClient } from './telemetryApi';

it.each([
  { device_id: 'other', battery_percent: 20, charging: false, firmware_version: '3.03', recorded_at: '2026-10-23T16:12:11Z' },
  { device_id: 'pulsar_susanto_x', battery_percent: 120, charging: false, firmware_version: '3.03', recorded_at: '2026-10-23T16:12:11Z' },
  { device_id: 'pulsar_susanto_x', battery_percent: 20, charging: false, firmware_version: '3.03', recorded_at: 'unknown' },
])('rejects malformed manual read responses (%#)', async (value) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
    .mockResolvedValueOnce(Response.json(value)));
  await expect(new TelemetryClient().read()).rejects.toThrow('Unexpected telemetry response.');
});

const settings = { device_id: 'pulsar_susanto_x', dpi: 1200, polling_rate_hz: 1000, active_profile_index: 0, active_stage_index: 2, recorded_at: '2026-10-23T18:30:12Z' };

it.each([
  { ...settings, device_id: 'other' }, { ...settings, dpi: 0 },
  { ...settings, polling_rate_hz: 123 }, { ...settings, active_profile_index: 4 },
  { ...settings, active_stage_index: 1.5 }, { ...settings, recorded_at: 'unknown' },
])('rejects malformed current-settings responses (%#)', async (value) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
    .mockResolvedValueOnce(Response.json(value)));
  await expect(new TelemetryClient().readSettings()).rejects.toThrow('Unexpected telemetry response.');
});

it.each([
  { device_id: 'other', responded: true, recorded_at: '2026-10-23T19:23:29Z' },
  { device_id: 'ajazz_ak820_pro', responded: false, recorded_at: '2026-10-23T19:23:29Z' },
  { device_id: 'ajazz_ak820_pro', responded: true, recorded_at: 'unknown' },
])('rejects malformed wired-control responses (%#)', async (value) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
    .mockResolvedValueOnce(Response.json(value)));
  await expect(new TelemetryClient().readControl()).rejects.toThrow('Unexpected control response.');
});

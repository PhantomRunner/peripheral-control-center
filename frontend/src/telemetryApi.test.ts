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

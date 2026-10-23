import { LocalApiClient, LocalApiError } from './localApi';
import type { TelemetrySnapshot } from './types';

export class TelemetryClient {
  private api = new LocalApiClient();

  async read(): Promise<TelemetrySnapshot> {
    let value: unknown;
    try {
      value = await this.api.request('/api/devices/pulsar_susanto_x/telemetry/read', 'POST', { vendor_tools_closed: true });
    } catch (cause) {
      if (cause instanceof LocalApiError) {
        if (cause.status === 409) throw new Error('Close other device-control tools before reading.');
        if (cause.status === 423) throw new Error('A device read is already running.');
        if (cause.status === 503) throw new Error('Hardware read was not confirmed. Check the receiver and close other control tools.');
      }
      throw cause;
    }
    if (typeof value !== 'object' || value === null) throw new Error('Unexpected telemetry response.');
    const data = value as Record<string, unknown>;
    if (data.device_id !== 'pulsar_susanto_x' || typeof data.battery_percent !== 'number'
      || !Number.isInteger(data.battery_percent) || data.battery_percent < 0 || data.battery_percent > 100
      || typeof data.charging !== 'boolean'
      || !(data.firmware_version === null || (typeof data.firmware_version === 'string' && /^[0-9]+\.[0-9a-f]{2}$/.test(data.firmware_version)))
      || typeof data.recorded_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(data.recorded_at) || !Number.isFinite(Date.parse(data.recorded_at))) {
      throw new Error('Unexpected telemetry response.');
    }
    return value as TelemetrySnapshot;
  }
}

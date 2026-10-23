import { LocalApiClient, LocalApiError } from './localApi';
import type { ConfigSnapshot, TelemetrySnapshot } from './types';

export class TelemetryClient {
  private api = new LocalApiClient();

  private async requestRead(path: string): Promise<Record<string, unknown>> {
    let value: unknown;
    try {
      value = await this.api.request(path, 'POST', { vendor_tools_closed: true });
    } catch (cause) {
      if (cause instanceof LocalApiError) {
        if (cause.status === 409) throw new Error('Close other device-control tools before reading.');
        if (cause.status === 423) throw new Error('A device read is already running.');
        if (cause.status === 503) throw new Error('Hardware read was not confirmed. Check the receiver and close other control tools.');
      }
      throw cause;
    }
    if (typeof value !== 'object' || value === null) throw new Error('Unexpected telemetry response.');
    return value as Record<string, unknown>;
  }

  async read(): Promise<TelemetrySnapshot> {
    const data = await this.requestRead('/api/devices/pulsar_susanto_x/telemetry/read');
    if (data.device_id !== 'pulsar_susanto_x' || typeof data.battery_percent !== 'number'
      || !Number.isInteger(data.battery_percent) || data.battery_percent < 0 || data.battery_percent > 100
      || typeof data.charging !== 'boolean'
      || !(data.firmware_version === null || (typeof data.firmware_version === 'string' && /^[0-9]+\.[0-9a-f]{2}$/.test(data.firmware_version)))
      || typeof data.recorded_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(data.recorded_at) || !Number.isFinite(Date.parse(data.recorded_at))) {
      throw new Error('Unexpected telemetry response.');
    }
    return data as TelemetrySnapshot;
  }

  async readSettings(): Promise<ConfigSnapshot> {
    const data = await this.requestRead('/api/devices/pulsar_susanto_x/settings/read');
    if (data.device_id !== 'pulsar_susanto_x' || typeof data.dpi !== 'number'
      || !Number.isInteger(data.dpi) || data.dpi < 1 || data.dpi > 32000
      || typeof data.polling_rate_hz !== 'number' || ![125, 250, 500, 1000, 2000, 4000, 8000].includes(data.polling_rate_hz)
      || typeof data.active_profile_index !== 'number' || !Number.isInteger(data.active_profile_index)
      || data.active_profile_index < 0 || data.active_profile_index > 3
      || typeof data.active_stage_index !== 'number' || !Number.isInteger(data.active_stage_index)
      || data.active_stage_index < 0 || data.active_stage_index > 5
      || typeof data.recorded_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(data.recorded_at) || !Number.isFinite(Date.parse(data.recorded_at))) {
      throw new Error('Unexpected telemetry response.');
    }
    return data as ConfigSnapshot;
  }
}

import { LocalApiClient, LocalApiError } from './localApi';
import { isSettings, type SettingsIntent } from './profilesApi';

export type RgbAcknowledgement = {
  status: 'acknowledged'; requested: Extract<SettingsIntent, { kind: 'keyboard' }>; actual: null;
};

export class SettingsClient {
  private api = new LocalApiClient();

  async apply(deviceId: string, desired: SettingsIntent, vendorToolsClosed = false, allowMemoryWrites = false): Promise<SettingsIntent | RgbAcknowledgement> {
    let value: unknown;
    try {
      value = await this.api.request(`/api/devices/${encodeURIComponent(deviceId)}/settings/apply`, 'POST', { settings: desired, vendor_tools_closed: vendorToolsClosed, allow_device_memory_writes: allowMemoryWrites });
    } catch (cause) {
      if (cause instanceof LocalApiError) {
        if (cause.status === 409) throw new Error('Apply is unavailable. Confirm tool closure and allow device-memory writes.');
        if (cause.status === 423) throw new Error('The device is busy. Close other device tools and retry.');
        if (cause.status === 422) throw new Error('These settings are not supported by the device adapter.');
        if (cause.status === 502) throw new Error('The write was not verified. Device state may have changed; check it before retrying.');
        if (cause.status === 503) throw new Error('Device access could not be established.');
      }
      throw cause;
    }
    if (typeof value === 'object' && value !== null && 'status' in value && value.status === 'acknowledged') {
      const result = value as Record<string, unknown>;
      const requested = result.requested_settings;
      if (deviceId !== 'ajazz_ak820_pro' || result.device_id !== deviceId || desired.kind !== 'keyboard'
        || !isSettings(requested) || requested.kind !== 'keyboard'
        || requested.rgb.color.toLowerCase() !== desired.rgb.color.toLowerCase()
        || requested.rgb.brightness_percent !== desired.rgb.brightness_percent
        || result.actual_settings !== null || result.readback_available !== false
        || result.persistence_verified !== false || result.may_persist !== true
        || result.feedback !== 'command_acknowledgements') {
        throw new Error('No matching RGB acknowledgement was received. Settings may have changed.');
      }
      return { status: 'acknowledged', requested, actual: null };
    }
    if (typeof value !== 'object' || value === null || !('status' in value) || value.status !== 'verified'
      || !('device_id' in value) || value.device_id !== deviceId || !('settings' in value) || !isSettings(value.settings)) {
      throw new Error('No valid readback confirmation was received. Device state may have changed.');
    }
    const actual = value.settings;
    if (actual.kind !== desired.kind
      || (desired.kind === 'mouse' && (actual.kind !== 'mouse' || (desired.dpi !== null && actual.dpi !== desired.dpi)
        || (desired.polling_rate_hz !== null && actual.polling_rate_hz !== desired.polling_rate_hz)))
      || (desired.kind === 'keyboard' && (actual.kind !== 'keyboard' || actual.rgb.mode !== desired.rgb.mode
        || actual.rgb.color.toLowerCase() !== desired.rgb.color.toLowerCase()
        || actual.rgb.brightness_percent !== desired.rgb.brightness_percent))) {
      throw new Error('Readback differs from the requested settings. Device state may have changed.');
    }
    return actual;
  }
}

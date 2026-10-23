import { LocalApiClient, LocalApiError } from './localApi';
import { isSettings, type SettingsIntent } from './profilesApi';

export class SettingsClient {
  private api = new LocalApiClient();

  async apply(deviceId: string, desired: SettingsIntent): Promise<SettingsIntent> {
    let value: unknown;
    try {
      value = await this.api.request(`/api/devices/${encodeURIComponent(deviceId)}/settings/apply`, 'POST', { settings: desired });
    } catch (cause) {
      if (cause instanceof LocalApiError) {
        if (cause.status === 409) throw new Error('No validated hardware writer is enabled for this device.');
        if (cause.status === 423) throw new Error('The device is busy. Close other device tools and retry.');
        if (cause.status === 422) throw new Error('These settings are not supported by the device adapter.');
        if (cause.status === 502) throw new Error('The write was not verified. Device state may have changed; check it before retrying.');
        if (cause.status === 503) throw new Error('Device access could not be established.');
      }
      throw cause;
    }
    if (typeof value !== 'object' || value === null || !('status' in value) || value.status !== 'verified'
      || !('device_id' in value) || value.device_id !== deviceId || !('settings' in value) || !isSettings(value.settings)) {
      throw new Error('No valid readback confirmation was received. Device state may have changed.');
    }
    const actual = value.settings;
    if (actual.kind !== desired.kind
      || (desired.kind === 'mouse' && (actual.kind !== 'mouse' || (desired.dpi !== null && actual.dpi !== desired.dpi)
        || (desired.polling_rate_hz !== null && actual.polling_rate_hz !== desired.polling_rate_hz)))
      || (desired.kind === 'keyboard' && (actual.kind !== 'keyboard' || JSON.stringify(actual.rgb) !== JSON.stringify(desired.rgb)))) {
      throw new Error('Readback differs from the requested settings. Device state may have changed.');
    }
    return actual;
  }
}

import type { Device, DeviceCapabilities } from './types';

const capabilityKeys: (keyof DeviceCapabilities)[] = [
  'usb_discovery', 'battery_read', 'dpi_read', 'polling_rate_read',
  'firmware_read', 'settings_write', 'control_read',
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNullableNumber(value: unknown): boolean {
  return value === null || (typeof value === 'number' && Number.isFinite(value));
}

function isDevice(value: unknown): value is Device {
  if (!isRecord(value) || !isRecord(value.capabilities) || !isRecord(value.connection)) return false;
  const { capabilities, connection } = value;
  const studio = value.studio_capabilities;
  return typeof value.id === 'string' && value.id.length > 0
    && typeof value.name === 'string'
    && (value.kind === 'mouse' || value.kind === 'keyboard')
    && (value.status === 'offline' || value.status === 'receiver_detected' || value.status === 'wired_detected')
    && Array.isArray(value.connected_usb_ids)
    && value.connected_usb_ids.every((id) => typeof id === 'string' && /^[0-9a-f]{4}:[0-9a-f]{4}$/.test(id))
    && isNullableNumber(value.battery_percent)
    && isNullableNumber(value.dpi)
    && isNullableNumber(value.polling_rate_hz)
    && (value.firmware_version === null || typeof value.firmware_version === 'string')
    && (value.telemetry_updated_at === null || (typeof value.telemetry_updated_at === 'string'
      && /^\d{4}-\d{2}-\d{2}T/.test(value.telemetry_updated_at) && Number.isFinite(Date.parse(value.telemetry_updated_at))))
    && (value.settings_updated_at === null || (typeof value.settings_updated_at === 'string'
      && /^\d{4}-\d{2}-\d{2}T/.test(value.settings_updated_at) && Number.isFinite(Date.parse(value.settings_updated_at))))
    && (value.control_responded === null || typeof value.control_responded === 'boolean')
    && (value.control_checked_at === null || (typeof value.control_checked_at === 'string'
      && /^\d{4}-\d{2}-\d{2}T/.test(value.control_checked_at) && Number.isFinite(Date.parse(value.control_checked_at))))
    && (value.driver_state === 'not_implemented' || value.driver_state === 'read_only' || value.driver_state === 'read_write')
    && (studio === undefined || studio === null || (isRecord(studio)
      && ['lighting_effects','clock_write','standby_write','screen_write'].every(key => typeof studio[key] === 'boolean')
      && typeof studio.max_screen_frames === 'number' && Number.isInteger(studio.max_screen_frames)
      && studio.max_screen_frames >= 0 && studio.max_screen_frames <= 120))
    && (value.write_options === null || (isRecord(value.write_options)
      && Array.isArray(value.write_options.dpi) && value.write_options.dpi.every((n) => typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= 32000)
      && Array.isArray(value.write_options.polling_rate_hz) && value.write_options.polling_rate_hz.every((n) => [125, 250, 500, 1000, 2000, 4000, 8000].includes(n))
      && typeof value.write_options.profile_index === 'number' && Number.isInteger(value.write_options.profile_index)
      && value.write_options.profile_index >= 0 && value.write_options.profile_index <= 3
      && typeof value.write_options.active_stage_index === 'number' && Number.isInteger(value.write_options.active_stage_index)
      && value.write_options.active_stage_index >= 0 && value.write_options.active_stage_index <= 5
      && typeof value.write_options.firmware_version === 'string' && /^[0-9]+\.[0-9a-f]{2}$/.test(value.write_options.firmware_version)))
    && (value.rgb_write_options === null || (isRecord(value.rgb_write_options)
      && value.rgb_write_options.mode === 'static' && value.rgb_write_options.feedback === 'acknowledged'
      && value.rgb_write_options.may_persist === true && Array.isArray(value.rgb_write_options.brightness_steps)
      && value.rgb_write_options.brightness_steps.every((n) => typeof n === 'number' && Number.isInteger(n) && n >= 0 && n <= 100)))
    && typeof value.note === 'string'
    && capabilityKeys.every((key) => typeof capabilities[key] === 'boolean')
    && connection.source === 'usb_enumeration'
    && typeof connection.wired_usb_present === 'boolean'
    && typeof connection.receiver_usb_present === 'boolean'
    && (connection.wireless_link_verified === null || typeof connection.wireless_link_verified === 'boolean');
}

export async function fetchDevices(signal: AbortSignal): Promise<Device[]> {
  let response: Response;
  try {
    response = await fetch('/api/devices', { cache: 'no-store', signal });
  } catch {
    throw new Error('Cannot reach the local backend.');
  }
  if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}.`);
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error('Unexpected API response.');
  }
  if (!isRecord(data) || !Array.isArray(data.devices) || !data.devices.every(isDevice)
    || new Set(data.devices.map((device) => device.id)).size !== data.devices.length) {
    throw new Error('Unexpected API response.');
  }
  return data.devices;
}

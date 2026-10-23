import type { Device, DeviceCapabilities } from './types';

const capabilityKeys: (keyof DeviceCapabilities)[] = [
  'usb_discovery', 'battery_read', 'dpi_read', 'polling_rate_read',
  'firmware_read', 'settings_write',
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
    && (value.driver_state === 'not_implemented' || value.driver_state === 'read_only')
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

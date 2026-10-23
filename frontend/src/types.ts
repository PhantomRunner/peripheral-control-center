export type DeviceCapabilities = {
  usb_discovery: boolean;
  battery_read: boolean;
  dpi_read: boolean;
  polling_rate_read: boolean;
  firmware_read: boolean;
  settings_write: boolean;
};

export type Device = {
  id: string;
  name: string;
  kind: 'mouse' | 'keyboard';
  status: 'offline' | 'receiver_detected' | 'wired_detected';
  connected_usb_ids: string[];
  battery_percent: number | null;
  dpi: number | null;
  polling_rate_hz: number | null;
  firmware_version: string | null;
  telemetry_updated_at: string | null;
  driver_state: 'not_implemented' | 'read_only';
  note: string;
  capabilities: DeviceCapabilities;
  connection: {
    source: 'usb_enumeration';
    wired_usb_present: boolean;
    receiver_usb_present: boolean;
    wireless_link_verified: boolean | null;
  };
};

export type TelemetrySnapshot = {
  device_id: 'pulsar_susanto_x';
  battery_percent: number;
  charging: boolean;
  firmware_version: string | null;
  recorded_at: string;
};

import type { Device } from '../types';

export const mouse: Device = {
  id: 'pulsar_susanto_x', name: 'Pulsar Susanto-X', kind: 'mouse',
  status: 'receiver_detected', connected_usb_ids: ['3710:5406'],
  battery_percent: null, dpi: null, polling_rate_hz: null, firmware_version: null,
  telemetry_updated_at: null,
  driver_state: 'not_implemented',
  note: '8K receiver detected. The mouse link and settings are not read yet.',
  capabilities: {
    usb_discovery: true, battery_read: false, dpi_read: false,
    polling_rate_read: false, firmware_read: false, settings_write: false,
  },
  connection: {
    source: 'usb_enumeration', wired_usb_present: false,
    receiver_usb_present: true, wireless_link_verified: null,
  },
};

export const keyboard: Device = {
  ...mouse, id: 'ajazz_ak820_pro', name: 'AJAZZ AK820 Pro', kind: 'keyboard',
  status: 'wired_detected', connected_usb_ids: ['0c45:8009', '0c45:fdfd'],
  note: 'Wired USB device detected. HID settings are not read yet.',
  connection: { ...mouse.connection, wired_usb_present: true },
};

export const offlineMouse: Device = {
  ...mouse, status: 'offline', connected_usb_ids: [], note: '8K receiver not detected.',
  connection: { ...mouse.connection, receiver_usb_present: false },
};

export function deviceResponse(devices: Device[] = [mouse, keyboard]): Response {
  return Response.json({ devices });
}

export function pendingRequest(_input: unknown, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  });
}

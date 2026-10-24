import type { Device } from './types';

// Readings and scan timestamps do not renew authorization. Connection/support changes do.
export function hardwareContext(device: Device, stale: boolean): string {
  return JSON.stringify([device.id, device.status, device.connection, stale,
    device.capabilities, device.write_options, device.rgb_write_options, device.studio_capabilities, device.performance_capabilities]);
}

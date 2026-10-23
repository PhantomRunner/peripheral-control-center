import type { Device, DeviceCapabilities } from '../types';
import { DeviceMetrics, DeviceStatus } from './DeviceCard';
import { TelemetryControls } from './TelemetryControls';
import { KeyboardControl } from './KeyboardControl';

const capabilities: [keyof DeviceCapabilities, string][] = [
  ['usb_discovery', 'USB discovery'], ['battery_read', 'Battery reading'],
  ['dpi_read', 'DPI reading'], ['polling_rate_read', 'Polling rate reading'],
  ['firmware_read', 'Firmware version reading'], ['settings_write', 'Settings changes'],
  ['control_read', 'Wired control check'],
];

export function DeviceDetails({ device, stale, onTelemetryRead }: { device: Device; stale: boolean; onTelemetryRead?: () => Promise<void> }) {
  const { connection } = device;
  return (
    <div className="device-details">
      <section className="panel" aria-labelledby="connection-title">
        <div className="panel-heading"><h2 id="connection-title">Connection</h2><DeviceStatus device={device} stale={stale} /></div>
        <p className="device-note">{device.note}</p>
        <dl className="facts">
          <div><dt>Observation source</dt><dd>USB enumeration</dd></div>
          <div><dt>Wired USB</dt><dd>{connection.wired_usb_present ? 'Detected' : 'Not detected'}</dd></div>
          <div><dt>USB receiver</dt><dd>{connection.receiver_usb_present ? 'Detected' : 'Not detected'}</dd></div>
          <div><dt>Wireless link</dt><dd>{connection.wireless_link_verified === null ? 'Not verified' : connection.wireless_link_verified ? 'Verified' : 'Disconnected'}</dd></div>
          <div><dt>Attached USB IDs</dt><dd className="usb-ids">{device.connected_usb_ids.join(' · ') || 'None'}</dd></div>
        </dl>
        {onTelemetryRead && device.id === 'ajazz_ak820_pro' && device.capabilities.control_read && <KeyboardControl device={device} stale={stale} onUpdated={onTelemetryRead} />}
      </section>
      <section className="panel" aria-labelledby="telemetry-title">
        <h2 id="telemetry-title">Telemetry</h2>
        <p className="device-note">{device.capabilities.battery_read || device.capabilities.firmware_read ? 'Readings update only on request. Polling is the stored device setting. Unsupported readings stay unavailable.' : 'Values stay unavailable until a validated live read is implemented.'}</p>
        <DeviceMetrics device={device} />
        <dl className="facts"><div><dt>Firmware version</dt><dd>{device.firmware_version ?? '—'}</dd></div></dl>
        {device.telemetry_updated_at && <p className="device-note">Last hardware read: {new Date(device.telemetry_updated_at).toLocaleString()}</p>}
        {device.settings_updated_at && <p className="device-note">Last DPI/polling read: {new Date(device.settings_updated_at).toLocaleString()}</p>}
        {onTelemetryRead && device.id === 'pulsar_susanto_x' && device.capabilities.battery_read && device.capabilities.firmware_read && <TelemetryControls device={device} stale={stale} onUpdated={onTelemetryRead} />}
      </section>
      <section className="panel capabilities" aria-labelledby="capabilities-title">
        <h2 id="capabilities-title">Adapter support</h2>
        <p className="device-note">Implemented operations are independent of whether USB hardware is attached.</p>
        <dl className="facts">
          {capabilities.map(([key, label]) => (
            <div key={key}><dt>{label}</dt><dd className={device.capabilities[key] ? 'supported' : ''}>{device.capabilities[key] ? 'Available' : 'Not implemented'}</dd></div>
          ))}
        </dl>
      </section>
    </div>
  );
}

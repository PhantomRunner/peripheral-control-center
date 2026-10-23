import type { Device } from '../types';

const statusLabels: Record<Device['status'], string> = {
  offline: 'USB not detected',
  receiver_detected: 'USB receiver detected',
  wired_detected: 'Wired USB detected',
};

export function DeviceStatus({ device, stale = false }: { device: Device; stale?: boolean }) {
  return (
    <span className={`pill ${stale ? 'stale' : device.status === 'offline' ? 'offline' : 'online'}`}>
      <span className="status-dot" aria-hidden="true" />
      {stale ? 'Last known: ' : ''}{statusLabels[device.status]}
    </span>
  );
}

export function DeviceMetrics({ device }: { device: Device }) {
  return (
    <dl className="metric-grid">
      <div><dt>Battery</dt><dd>{device.battery_percent === null ? '—' : `${device.battery_percent}%`}</dd></div>
      <div><dt>Polling</dt><dd>{device.polling_rate_hz === null ? '—' : `${device.polling_rate_hz} Hz`}</dd></div>
      <div><dt>DPI</dt><dd>{device.dpi ?? '—'}</dd></div>
    </dl>
  );
}

export function DeviceCard({ device, stale }: { device: Device; stale: boolean }) {
  return (
    <article className="device-card" aria-label={device.name}>
      <div className="card-top">
        <div className="device-icon" aria-hidden="true">{device.kind === 'mouse' ? '◉' : '⌨'}</div>
        <DeviceStatus device={device} stale={stale} />
      </div>
      <h3 className="device-name"><a href={`#/devices/${encodeURIComponent(device.id)}`}>{device.name}</a></h3>
      <div className="device-type">{device.kind === 'mouse' ? 'Gaming mouse' : 'Mechanical keyboard'}</div>
      <p className="device-note">{device.note}</p>
      <DeviceMetrics device={device} />
      <div className="card-footer">
        <span className="usb-ids">{device.connected_usb_ids.join(' · ') || 'No USB ID detected'}</span>
        <a className="detail-link" href={`#/devices/${encodeURIComponent(device.id)}`} aria-label={`View ${device.name} details`}>View details →</a>
      </div>
    </article>
  );
}

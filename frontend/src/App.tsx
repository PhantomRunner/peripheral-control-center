import { useCallback, useEffect, useState } from 'react';

type Device = {
  id: string;
  name: string;
  kind: 'mouse' | 'keyboard';
  status: 'offline' | 'receiver_detected' | 'wired_detected';
  connected_usb_ids: string[];
  battery_percent: number | null;
  dpi: number | null;
  polling_rate_hz: number | null;
  driver_state: 'not_implemented';
  note: string;
};

type DevicesResponse = { devices: Device[] };

const statusLabels: Record<Device['status'], string> = {
  offline: 'Not detected',
  receiver_detected: 'USB receiver detected',
  wired_detected: 'USB wired detected',
};

function DeviceCard({ device }: { device: Device }) {
  const active = device.status !== 'offline';
  return (
    <article className="device-card">
      <div className="card-top">
        <div className="device-icon" aria-hidden="true">{device.kind === 'mouse' ? '◉' : '⌨'}</div>
        <span className={`pill ${active ? 'online' : 'offline'}`}>
          <span className="status-dot" />{statusLabels[device.status]}
        </span>
      </div>
      <div className="device-name">{device.name}</div>
      <div className="device-type">{device.kind === 'mouse' ? 'Gaming mouse' : 'Mechanical keyboard'}</div>
      <p className="device-note">{device.note}</p>
      <div className="divider" />
      <div className="metric-grid">
        <div><span className="metric-label">Battery</span><strong>{device.battery_percent === null ? '—' : `${device.battery_percent}%`}</strong></div>
        <div><span className="metric-label">Polling</span><strong>{device.polling_rate_hz === null ? '—' : `${device.polling_rate_hz} Hz`}</strong></div>
        <div><span className="metric-label">DPI</span><strong>{device.dpi === null ? '—' : device.dpi}</strong></div>
      </div>
      <div className="card-footer">
        <div className="usb-ids">{device.connected_usb_ids.length ? device.connected_usb_ids.join(' · ') : 'No USB ID detected'}</div>
        <span className="read-only">Read-only discovery</span>
      </div>
    </article>
  );
}

export default function App() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastChecked, setLastChecked] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const response = await fetch('/api/devices', { cache: 'no-store' });
      if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}`);
      const data = (await response.json()) as DevicesResponse;
      if (!Array.isArray(data.devices)) throw new Error('Unexpected API response');
      setDevices(data.devices);
      setError(null);
      setLastChecked(new Date().toLocaleTimeString());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Cannot reach local backend');
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => { void refresh(); }, 15_000);
    return () => clearInterval(interval);
  }, [refresh]);

  const detected = devices?.filter((device) => device.status !== 'offline').length ?? 0;
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="logo"><span className="logo-mark">P</span><span>PCC <small>Local</small></span></div>
        <div className="nav-section">WORKSPACE</div>
        <div className="nav-item selected">▦ <span>Dashboard</span></div>
        <div className="nav-item disabled">◫ <span>Profiles <small>later</small></span></div>
        <div className="nav-item disabled">⚙ <span>Preferences <small>later</small></span></div>
        <div className="side-bottom"><span className="status-dot" /> Local mode<br/><small>Only this computer can access the API.</small></div>
      </aside>
      <main className="content">
        <header className="page-header">
          <div><div className="eyebrow">CONTROL PANEL / OVERVIEW</div><h1>Your peripherals<span>.</span></h1><p>One workspace. Every device. No vendor lock-in.</p></div>
          <button className="refresh" onClick={() => { void refresh(); }} disabled={refreshing}>{refreshing ? 'Checking…' : '↻ Refresh'}</button>
        </header>
        <section className="summary">
          <div><div className="summary-label">Known devices</div><strong>{devices?.length ?? '—'}</strong></div>
          <div><div className="summary-label">USB hardware detected</div><strong>{devices ? detected : '—'}</strong></div>
          <div><div className="summary-label">Driver support</div><strong className="coming">Coming next</strong></div>
        </section>
        <div className="section-title"><h2>Devices</h2><span>{lastChecked ? `Last scan ${lastChecked}` : 'Waiting for backend'}</span></div>
        {error && <div className="error" role="alert">Backend unavailable: {error}. Start FastAPI on 127.0.0.1:8000 and refresh.</div>}
        {devices ? <section className="devices">{devices.map((device) => <DeviceCard key={device.id} device={device} />)}</section> : <p className="loading">Loading devices from the local API…</p>}
        <section className="notice"><span className="notice-icon">i</span><div><strong>Hardware-safe mode</strong><p>This starter detects USB IDs only. It does not read battery, change DPI, send RGB commands, or modify firmware. A detected dongle does not prove its wireless device is awake.</p></div></section>
      </main>
    </div>
  );
}

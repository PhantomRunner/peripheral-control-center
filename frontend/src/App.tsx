import { Fragment, useEffect, useRef, useState } from 'react';
import { DeviceCard } from './components/DeviceCard';
import { DeviceDetails } from './components/DeviceDetails';
import { ProfilePanel } from './components/ProfilePanel';
import { useDevices } from './hooks/useDevices';

function getDeviceId(hash: string): string | null {
  if (!hash || hash === '#' || hash === '#/') return null;
  try {
    return hash.startsWith('#/devices/') ? decodeURIComponent(hash.slice(10)) : '';
  } catch {
    return '';
  }
}

export default function App() {
  const { devices, error, refreshing, lastChecked, disconnected, stale, refresh } = useDevices();
  const [hash, setHash] = useState(window.location.hash);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const navigate = () => setHash(window.location.hash);
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  useEffect(() => {
    heading.current?.focus();
  }, [hash]);

  const deviceId = getDeviceId(hash);
  const selected = devices?.find((device) => device.id === deviceId);
  const detail = deviceId !== null;
  const title = detail ? selected?.name ?? (devices ? 'Device not found' : 'Device details') : 'Your peripherals';
  const detected = devices?.filter((device) => device.status !== 'offline').length;
  return (
    <div className="layout">
      <a className="skip-link" href="#main" onClick={(event) => { event.preventDefault(); document.getElementById('main')?.focus(); }}>Skip to content</a>
      <aside className="sidebar">
        <a className="logo" href="#/" aria-label="PCC home"><span className="logo-mark">P</span><span>PCC <small>Local</small></span></a>
        <nav aria-label="Main navigation">
          <div className="nav-section">WORKSPACE</div>
          <a className={`nav-item ${!detail ? 'selected' : ''}`} href="#/" aria-current={!detail ? 'page' : undefined}>▦ <span>Dashboard</span></a>
          {(devices ?? []).map((device) => <a key={device.id} className={`nav-item ${selected?.id === device.id ? 'selected' : ''}`} href={`#/devices/${encodeURIComponent(device.id)}`} aria-current={selected?.id === device.id ? 'page' : undefined}>{device.kind === 'mouse' ? '◉' : '⌨'} <span>{device.name}</span></a>)}
        </nav>
        <div className="side-bottom">Local mode<small>Read-only USB discovery</small></div>
      </aside>
      <main id="main" className="content" tabIndex={-1}>
        <header className="page-header">
          <div><div className="eyebrow">CONTROL PANEL / {detail ? 'DEVICE DETAILS' : 'OVERVIEW'}</div><h1 ref={heading} tabIndex={-1}>{title}<span>.</span></h1><p>{detail ? 'USB presence, telemetry and adapter support.' : 'One workspace. Every device. No vendor lock-in.'}</p></div>
          <button className="refresh" onClick={() => { void refresh(); }} disabled={refreshing}>{refreshing ? 'Checking…' : error ? 'Retry connection' : '↻ Refresh'}</button>
        </header>
        {detail && <a className="back-link" href="#/">← All devices</a>}
        {!detail && <section className="summary" aria-label="Device overview">
          <div><div className="summary-label">Known devices</div><strong>{devices?.length ?? '—'}</strong></div>
          <div><div className="summary-label">USB hardware detected</div><strong>{stale ? '—' : detected ?? '—'}</strong></div>
          <div><div className="summary-label">Adapter mode</div><strong className="coming">USB discovery</strong></div>
        </section>}
        <div className="section-title"><h2>{detail ? 'Device status' : 'Devices'}</h2><span>{lastChecked ? `${stale ? 'Last successful scan' : 'Last scan'} ${lastChecked.toLocaleTimeString()}` : 'Waiting for backend'}</span></div>
        {error && <div className="error" role="alert"><strong>Backend unavailable.</strong> {error} {stale ? 'Showing last known data; current USB presence is unknown.' : 'Start the local backend and retry.'}</div>}
        {stale && <p className="stale-label" role="status">Last known data · connection and readings may be outdated.</p>}
        {!stale && disconnected.length > 0 && <p className="disconnect" role="status">USB disconnected since last scan: {disconnected.join(', ')}.</p>}
        {devices === null ? (
          !error && <div className="empty-state" role="status"><span className="loading-dot" aria-hidden="true" /><h3>Checking USB devices</h3><p>Loading devices from the local API…</p></div>
        ) : detail ? (
          selected ? <Fragment key={selected.id}><DeviceDetails device={selected} stale={stale} onTelemetryRead={refresh} /><ProfilePanel device={selected} stale={stale} onUpdated={refresh} /></Fragment> : <div className="empty-state"><h3>Device not found</h3><p>This device is not registered. Choose a device from the dashboard.</p><a href="#/">Go to dashboard</a></div>
        ) : devices.length ? (
          <section className="devices" aria-label="Known peripherals">{devices.map((device) => <DeviceCard key={device.id} device={device} stale={stale} />)}</section>
        ) : <div className="empty-state"><h3>No registered devices</h3><p>The backend returned no known device adapters.</p></div>}
        <section className="notice"><span className="notice-icon" aria-hidden="true">i</span><div><strong>Read-only discovery</strong><p>USB detection does not verify a wireless link. Hardware reads are manual; unsupported readings stay unavailable.</p></div></section>
      </main>
    </div>
  );
}

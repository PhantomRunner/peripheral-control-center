import { useId, useRef, useState } from 'react';
import { ApplyControls } from '../components/ApplyControls';
import { DeviceDetails } from '../components/DeviceDetails';
import { DeviceStatus } from '../components/DeviceCard';
import { ProfilePanel } from '../components/ProfilePanel';
import type { Device } from '../types';
import './mouse.css';

export function MouseWorkspace({ device, stale, onUpdated }: { device: Device; stale: boolean; onUpdated: () => Promise<void> }) {
  const [tab, setTab] = useState('dpi');
  const [dpi, setDpi] = useState<number | null>(null);
  const [polling, setPolling] = useState<number | null>(null);
  const [field, setField] = useState<'dpi' | 'polling'>('dpi');
  const [busy, setBusy] = useState(false);
  const id = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const tabs = [['dpi', 'DPI & polling'], ['sensor', 'Sensor'], ['device', 'Device & profiles']] as const;
  const desired = { kind: 'mouse' as const, dpi: field === 'dpi' ? dpi : null, polling_rate_hz: field === 'polling' ? polling : null };
  return <div className="mouse-workspace">
    <div className="mouse-status"><span>SUSANTO-X · PERFORMANCE</span><DeviceStatus device={device} stale={stale} /></div>
    <div className="mouse-tabs" role="tablist" aria-label="Mouse workspace">{tabs.map(([key, label], index) => <button key={key} ref={el => { buttons.current[index] = el; }} type="button" role="tab" id={`${id}-${key}`} aria-selected={tab === key} aria-controls={`${id}-panel`} tabIndex={tab === key ? 0 : -1} onClick={() => setTab(key)} onKeyDown={event => {
      let next = index;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault(); setTab(tabs[next][0]); buttons.current[next]?.focus();
    }}>{label}</button>)}</div>
    <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${tab}`}>
      {tab === 'dpi' && <div className="mouse-grid">
        <section className="panel mouse-preview"><h2>Precision, your way.</h2><MousePreview rotation={0} /><dl className="facts"><div><dt>Last observed DPI</dt><dd>{stale ? '—' : device.dpi ?? '—'}</dd></div><div><dt>Stored polling</dt><dd>{!stale && device.polling_rate_hz !== null ? `${device.polling_rate_hz} Hz` : '—'}</dd></div></dl><p className="device-note">Receiver presence does not confirm a wireless link. Read current settings in Device & profiles.</p></section>
        <section className="panel mouse-form" aria-label="Current stage settings"><h2>DPI & polling</h2><p className="device-note">Local draft · one setting per Apply. New stages and sensor controls require exact-device validation.</p>
          <fieldset disabled={busy}><label>Setting to apply<select value={field} onChange={event => setField(event.target.value as typeof field)}><option value="dpi">Current stage DPI</option><option value="polling">Polling rate</option></select></label>
            <label>Current stage DPI (draft)<input type="number" min={1} max={32000} value={dpi ?? ''} placeholder="Enter DPI" onChange={event => setDpi(event.target.value === '' ? null : Number(event.target.value))} /></label>
            <label>Polling rate (draft)<select value={polling ?? ''} onChange={event => setPolling(event.target.value === '' ? null : Number(event.target.value))}><option value="">Choose polling rate</option>{[125,250,500,1000,2000,4000,8000].map(rate => <option key={rate} value={rate}>{rate} Hz</option>)}</select></label>
          </fieldset>
          <ApplyControls device={device} stale={stale} desired={desired} busy={busy} onBusy={setBusy} onUpdated={onUpdated} disabledReason={(field === 'dpi' ? dpi : polling) === null ? 'Choose a draft value before Apply.' : undefined} />
        </section>
      </div>}
      {tab === 'sensor' && <section className="panel"><h2>Sensor tuning</h2><p className="device-note">LOD, debounce, Motion Sync, Angle Snap, Ripple Control, Turbo and rotation are awaiting exact-device validation. No sensor commands are enabled.</p></section>}
      {tab === 'device' && <><DeviceDetails device={device} stale={stale} onTelemetryRead={onUpdated} /><ProfilePanel device={device} stale={stale} onUpdated={onUpdated} /></>}
    </div>
  </div>;
}

export function MousePreview({ rotation }: { rotation: number }) {
  return <svg className="mouse-illustration" viewBox="0 0 360 330" role="img" aria-label={`Mouse schematic; draft sensor rotation ${rotation} degrees`}>
    <path d="M180 25C113 25 94 78 94 148l-9 76c-4 49 35 78 95 78s99-29 95-78l-9-76c0-70-19-123-86-123Z" fill="#172237" stroke="#586782" strokeWidth="2" />
    <path d="M180 26v113M96 136c52 16 116 16 168 0" fill="none" stroke="#586782" strokeWidth="2" />
    <rect x="169" y="58" width="22" height="44" rx="10" fill="#9c91f7" />
    <path d="M120 213h120M180 153v119" stroke="#394b69" strokeDasharray="5 5" />
    <g transform={`rotate(${rotation} 180 213)`}><path d="M180 168v90m-18-72 18-18 18 18" fill="none" stroke="#b9b1ff" strokeWidth="3" /><circle cx="180" cy="213" r="12" fill="#222f47" stroke="#b9b1ff" strokeWidth="2" /></g>
    <text x="180" y="321" textAnchor="middle" fill="#aab9d1" fontSize="11">Schematic · local preview</text>
  </svg>;
}

import { useId, useRef, useState } from 'react';
import { DeviceDetails } from '../components/DeviceDetails';
import { DeviceStatus } from '../components/DeviceCard';
import { ProfilePanel } from '../components/ProfilePanel';
import { MousePreview } from './MousePreview';
import type { Device } from '../types';
import { usePerformance } from './usePerformance';
import { PerformanceReadControl } from './PerformanceControls';
import { EMPTY_STAGE_DRAFT,StagePanel } from './StagePanel';
import { EMPTY_SENSOR_DRAFT,SensorPanel } from './SensorPanel';
import { LegacyDpiControls,type LegacyDpiDraft } from './LegacyDpiControls';
import './mouse.css';

export function MouseWorkspace({ device, stale, onUpdated }: { device: Device; stale: boolean; onUpdated: () => Promise<void> }) {
  const [tab, setTab] = useState('dpi');
  const [legacyDraft,setLegacyDraft]=useState<LegacyDpiDraft>({dpi:null,polling:null,field:'dpi'});
  const [busy, setBusy] = useState(false);
  const [stageDraft,setStageDraft]=useState(EMPTY_STAGE_DRAFT);
  const [sensorDraft,setSensorDraft]=useState(EMPTY_SENSOR_DRAFT);
  const performance=usePerformance(device,stale,onUpdated);
  const id = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const tabs = [['dpi', 'DPI & polling'], ['sensor', 'Sensor'], ['device', 'Device & profiles']] as const;
  const legacy=<LegacyDpiControls device={device} stale={stale} draft={legacyDraft} onChange={setLegacyDraft} busy={busy||performance.busy} onBusy={setBusy} onUpdated={async()=>{performance.clear();await onUpdated();}} />;
  const active=performance.snapshot?.stages[performance.snapshot.active_stage_index];
  const observedDpi=active?(active.x===active.y?active.x??'—':`${active.x??'—'} / ${active.y??'—'}`):device.dpi??'—';
  const observedPolling=performance.snapshot?performance.snapshot.polling_rate_hz:device.polling_rate_hz;
  return <div className="mouse-workspace">
    <div className="mouse-status"><span>SUSANTO-X · PERFORMANCE</span><DeviceStatus device={device} stale={stale} /></div>
    <div className="mouse-tabs" role="tablist" aria-label="Mouse workspace">{tabs.map(([key, label], index) => <button key={key} disabled={busy} ref={el => { buttons.current[index] = el; }} type="button" role="tab" id={`${id}-${key}`} aria-selected={tab === key} aria-controls={`${id}-panel`} tabIndex={tab === key ? 0 : -1} onClick={() => setTab(key)} onKeyDown={event => {
      let next = index;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault(); setTab(tabs[next][0]); buttons.current[next]?.focus();
    }}>{label}</button>)}</div>
    <PerformanceReadControl performance={performance} blocked={busy} />
    <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${tab}`}>
      {tab === 'dpi' && <div className="mouse-grid">
        <section className="panel mouse-preview" aria-label="Mouse overview"><h2>Precision, your way.</h2><MousePreview rotation={0} /><dl className="facts"><div><dt>Last observed DPI</dt><dd>{stale?'—':observedDpi}</dd></div><div><dt>Stored polling</dt><dd>{!stale&&observedPolling!==null?`${observedPolling} Hz`:'—'}</dd></div></dl><p className="device-note">Receiver presence does not confirm a wireless link. {performance.snapshot?'Values come from the timestamped performance snapshot above.':'Read current settings in Device & profiles.'}</p></section>
        {performance.snapshot?<StagePanel device={device} performance={performance} draft={stageDraft} onChange={setStageDraft} blocked={busy} />:legacy}
      </div>}
      {tab==='dpi'&&(performance.snapshot?<details className="mouse-legacy"><summary>Previously verified current-stage controls</summary>{legacy}</details>:<section className="panel mouse-stage-notice"><h2>DPI stages</h2><p className="device-note">Read the mouse to show its configured DPI stages. The stage editor requires a validated performance reader.</p></section>)}
      {tab === 'sensor' && <SensorPanel device={device} performance={performance} draft={sensorDraft} onChange={setSensorDraft} blocked={busy} />}
      {tab === 'device' && <><DeviceDetails device={device} stale={stale} onTelemetryRead={onUpdated} /><ProfilePanel device={device} stale={stale} onUpdated={async()=>{performance.clear();await onUpdated();}} /></>}
    </div>
  </div>;
}

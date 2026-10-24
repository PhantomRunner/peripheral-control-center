import { useMemo } from 'react';
import { ApplyControls } from '../components/ApplyControls';
import type { Device } from '../types';

export type LegacyDpiDraft={dpi:number|null;polling:number|null;field:'dpi'|'polling'};
export function LegacyDpiControls({device,stale,draft,onChange,busy,onBusy,onUpdated}:{device:Device;stale:boolean;draft:LegacyDpiDraft;onChange:(next:LegacyDpiDraft)=>void;busy:boolean;onBusy:(value:boolean)=>void;onUpdated:()=>Promise<void>}) {
  const {dpi,polling,field}=draft;
  const desired=useMemo(()=>({kind:'mouse' as const,dpi:field==='dpi'?dpi:null,polling_rate_hz:field==='polling'?polling:null}),[field,dpi,polling]);
  return <section className="panel mouse-form" aria-label="Current stage settings"><h2>Verified current-stage controls</h2><p className="device-note">One setting per Apply, using the existing verified adapter and its profile/stage restrictions.</p>
    <fieldset disabled={busy}><label>Setting to apply<select value={field} onChange={e=>onChange({...draft,field:e.target.value as LegacyDpiDraft['field']})}><option value="dpi">Current stage DPI</option><option value="polling">Polling rate</option></select></label>
      <label>Current stage DPI (draft)<input type="number" min={1} max={32000} value={dpi??''} placeholder="Enter DPI" onChange={e=>onChange({...draft,dpi:e.target.value===''?null:Number(e.target.value)})} /></label>
      <label>Polling rate (draft)<select value={polling??''} onChange={e=>onChange({...draft,polling:e.target.value===''?null:Number(e.target.value)})}><option value="">Choose polling rate</option>{[125,250,500,1000,2000,4000,8000].map(rate=><option key={rate} value={rate}>{rate} Hz</option>)}</select></label>
    </fieldset>
    <ApplyControls device={device} stale={stale} desired={desired} busy={busy} onBusy={onBusy} onUpdated={onUpdated} disabledReason={(field==='dpi'?dpi:polling)===null?'Choose a draft value before Apply.':undefined} />
  </section>;
}

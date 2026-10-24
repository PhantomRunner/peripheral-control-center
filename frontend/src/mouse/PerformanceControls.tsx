import { useEffect,useState } from 'react';
import type { Device } from '../types';
import { supportedAction,type PerformanceAction } from './performance';
import type { PerformanceState } from './usePerformance';

export function PerformanceReadControl({performance,blocked}:{performance:PerformanceState;blocked:boolean}) {
  const [closed,setClosed]=useState(false);
  useEffect(()=>{setClosed(false);},[performance.context]);
  return <section className="panel mouse-readbar" aria-label="Performance reading"><div><strong>Current stages & sensor</strong><p className="device-note">{performance.snapshot?`Observed ${new Date(performance.snapshot.recorded_at).toLocaleString()} · onboard profile ${performance.snapshot.active_profile_index+1}`:'No performance snapshot. Read explicitly to populate current values.'}</p></div>
    <label className="tool-confirmation"><input type="checkbox" checked={closed} disabled={!performance.readEnabled||performance.busy||blocked} onChange={e=>setClosed(e.target.checked)} />Other device-control tools are closed for performance reading</label>
    <button className="secondary" type="button" disabled={!performance.readEnabled||performance.busy||blocked||!closed} onClick={()=>{setClosed(false);void performance.run();}}>{performance.busy?'Working with mouse…':'Read stages & sensor'}</button>
    {!performance.readEnabled&&<p className="device-note">Requires connected receiver and a validated performance reader. Existing manual reads remain in Device & profiles.</p>}
    {performance.message&&<p role={performance.message.error?'alert':'status'} className={performance.message.error?'error':'profile-notice'}>{performance.message.text}</p>}
  </section>;
}

export function PerformanceApplyControl({device,performance,action,blocked}:{device:Device;performance:PerformanceState;action:PerformanceAction|null;blocked:boolean}) {
  const [closed,setClosed]=useState(false),[memory,setMemory]=useState(false);
  const actionKey=JSON.stringify(action);
  useEffect(()=>{setClosed(false);setMemory(false);},[performance.context,actionKey,performance.snapshot]);
  const available=performance.readEnabled && action!==null && supportedAction(device.performance_capabilities,action,performance.snapshot);
  return <div className="apply-controls">
    <label className="tool-confirmation"><input type="checkbox" checked={closed} disabled={!available||performance.busy||blocked} onChange={e=>setClosed(e.target.checked)} />Other device-control tools are closed for this change</label>
    <label className="tool-confirmation"><input type="checkbox" checked={memory} disabled={!available||performance.busy||blocked} onChange={e=>setMemory(e.target.checked)} />Allow this change to persist in device memory</label>
    <button className="refresh" type="button" disabled={!available||performance.busy||blocked||!closed||!memory} onClick={()=>{if(action){setClosed(false);setMemory(false);void performance.run(action);}}}>Apply selected change</button>
    <p className="device-note">{available?'One selected change only. Device readback is required; an ACK is insufficient.':'Read current settings and choose a value validated for this exact mouse. Unverified writes are unavailable.'}</p>
  </div>;
}

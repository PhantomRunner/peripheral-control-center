import type { Device } from '../types';
import { PerformanceApplyControl } from './PerformanceControls';
import type { PerformanceAction } from './performance';
import type { PerformanceState } from './usePerformance';

export type StageDraft={operation:'stage_dpi'|'active_stage'|'polling_rate';index:number;dpi:Record<number,number|null>;polling:number|null};
export const EMPTY_STAGE_DRAFT:StageDraft={operation:'stage_dpi',index:0,dpi:{},polling:null};

export function StagePanel({device,performance,draft,onChange,blocked}:{device:Device;performance:PerformanceState;draft:StageDraft;onChange:(next:StageDraft)=>void;blocked:boolean}) {
  const snapshot=performance.snapshot;
  const dpi=draft.dpi[draft.index]===undefined?snapshot?.stages[draft.index]?.x??null:draft.dpi[draft.index];
  const polling=draft.polling??snapshot?.polling_rate_hz??null;
  const action:PerformanceAction|null=draft.operation==='stage_dpi'?(dpi===null?null:{operation:'stage_dpi',stage_index:draft.index,dpi})
    :draft.operation==='active_stage'?{operation:'active_stage',stage_index:draft.index}:polling===null?null:{operation:'polling_rate',hz:polling};
  return <section className="panel mouse-form" aria-label="DPI stage editor"><h2>DPI stages</h2><p className="device-note">Edit existing stages in the current onboard profile. Stage count and other profiles stay unchanged.</p>
    {snapshot?<div className="mouse-stage-list" aria-label="Observed DPI stages">{snapshot.stages.map(stage=><button type="button" key={stage.index} aria-label={`Stage ${stage.index+1}${snapshot.active_stage_index===stage.index?' · active':''} ${stage.x??'unavailable'}${stage.x!==stage.y?` / ${stage.y??'unavailable'}`:''} DPI`} disabled={performance.busy||blocked} aria-pressed={draft.index===stage.index} onClick={()=>onChange({...draft,index:stage.index})}><span>Stage {stage.index+1}{snapshot.active_stage_index===stage.index?' · active':''}</span><strong>{stage.x??'—'}{stage.x!==stage.y?` / ${stage.y??'—'}`:''}</strong><small>{stage.x!==stage.y?'X / Y DPI':'DPI'}</small></button>)}</div>:<p className="mouse-empty">Read the mouse to show its configured DPI stages.</p>}
    <fieldset disabled={performance.busy||blocked||!snapshot}>
      <label>Performance change<select value={draft.operation} onChange={e=>onChange({...draft,operation:e.target.value as StageDraft['operation']})}><option value="stage_dpi">Edit selected stage DPI</option><option value="active_stage">Select active DPI stage</option><option value="polling_rate">Polling rate</option></select></label>
      {draft.operation==='stage_dpi'&&<label>Selected stage DPI (draft)<input type="number" min={10} max={32000} value={dpi??''} placeholder="Unavailable" onChange={e=>onChange({...draft,dpi:{...draft.dpi,[draft.index]:e.target.value===''?null:Number(e.target.value)}})} /></label>}
      {draft.operation==='active_stage'&&<p className="device-note">Select stage {draft.index+1} using the observed stage buttons above. This changes the active stage only.</p>}
      {draft.operation==='polling_rate'&&<label>Performance polling rate (draft)<select value={polling??''} onChange={e=>onChange({...draft,polling:e.target.value===''?null:Number(e.target.value)})}><option value="">Unavailable</option>{[125,250,500,1000,2000,4000,8000].map(hz=><option key={hz} value={hz}>{hz} Hz</option>)}</select></label>}
    </fieldset>
    {draft.operation==='stage_dpi'&&<p className="device-note">Draft uses equal X/Y. Observed asymmetric axes remain visible above. Steps: 10 DPI through 10240, 50 through 25600, then 100.</p>}
    <PerformanceApplyControl device={device} performance={performance} action={action} blocked={blocked} />
  </section>;
}

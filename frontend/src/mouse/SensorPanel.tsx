import type { Device } from '../types';
import { MousePreview } from './MousePreview';
import { PerformanceApplyControl } from './PerformanceControls';
import type { PerformanceAction,SensorParameter } from './performance';
import type { PerformanceState } from './usePerformance';

export const SENSOR_LABELS:Record<SensorParameter,string>={lod:'Lift-off distance',debounce:'Debounce',motion_sync:'Motion Sync',angle_snap:'Angle Snap',ripple_control:'Ripple Control',turbo:'Turbo Mode',rotation:'Sensor Rotation'};
export type SensorDraft={parameter:SensorParameter;values:Partial<Record<SensorParameter,number|boolean|null>>};
export const EMPTY_SENSOR_DRAFT:SensorDraft={parameter:'lod',values:{}};

export function SensorPanel({device,performance,draft,onChange,blocked}:{device:Device;performance:PerformanceState;draft:SensorDraft;onChange:(next:SensorDraft)=>void;blocked:boolean}) {
  const name=draft.parameter;
  const value=draft.values[name]===undefined?performance.snapshot?.sensor[name]??null:draft.values[name];
  const setValue=(next:number|boolean|null)=>onChange({...draft,values:{...draft.values,[name]:next}});
  const rotation=draft.values.rotation===undefined?performance.snapshot?.sensor.rotation??null:draft.values.rotation;
  const action:PerformanceAction|null=value===null?null:name==='lod'?{operation:'lod',millimetres:Number(value)}:name==='debounce'?{operation:'debounce',milliseconds:Number(value)}:name==='rotation'?{operation:'rotation',degrees:Number(value)}:{operation:name,enabled:Boolean(value)};
  return <div className="mouse-grid"><section className="panel mouse-preview"><h2>Sensor tuning</h2><MousePreview rotation={typeof rotation==='number'?rotation:0} /><p className="device-note">{rotation===null?'Rotation unavailable · neutral schematic.':`Local rotation preview: ${rotation}°. Preview does not change the mouse.`}</p><dl className="facts">{(Object.keys(SENSOR_LABELS) as SensorParameter[]).map(key=>{const observed=performance.snapshot?.sensor[key]??null;return <div key={key}><dt>{SENSOR_LABELS[key]}</dt><dd>{observed===null?'—':typeof observed==='boolean'?observed?'On':'Off':`${observed}${key==='rotation'?'°':key==='lod'?' mm':key==='debounce'?' ms':''}`}</dd></div>;})}</dl></section>
    <section className="panel mouse-form" aria-label="Sensor editor"><h2>Sensor settings</h2><p className="device-note">Readings and local drafts are separate. New commands stay blocked until validated on your PSSTX21.</p>
      <fieldset disabled={performance.busy||blocked}><label>Sensor parameter<select value={name} onChange={e=>onChange({...draft,parameter:e.target.value as SensorParameter})}>{Object.entries(SENSOR_LABELS).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        {name==='lod'?<label>Lift-off distance (draft)<select value={value===null?'':String(value)} onChange={e=>setValue(e.target.value===''?null:Number(e.target.value))}><option value="">Choose distance</option>{[0.7,1,2].map(v=><option key={v} value={v}>{v} mm</option>)}</select></label>
          :name==='debounce'||name==='rotation'?<label>{SENSOR_LABELS[name]} (draft)<input type="number" min={name==='rotation'?-30:0} max={name==='rotation'?30:15} step={1} value={typeof value==='number'?value:''} placeholder="Enter local draft" onChange={e=>setValue(e.target.value===''?null:Number(e.target.value))} /></label>
          :<label>{SENSOR_LABELS[name]} (draft)<select value={value===null?'':String(value)} onChange={e=>setValue(e.target.value===''?null:e.target.value==='true')}><option value="">Choose state</option><option value="false">Off</option><option value="true">On</option></select></label>}
      </fieldset>
      <PerformanceApplyControl device={device} performance={performance} action={action} blocked={blocked} />
    </section>
  </div>;
}

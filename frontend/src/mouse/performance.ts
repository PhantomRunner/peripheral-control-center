export const PARAMETERS = ['stage_dpi','active_stage','polling_rate','lod','debounce','motion_sync','angle_snap','ripple_control','turbo','rotation'] as const;
export type Parameter = typeof PARAMETERS[number];
export type SensorParameter = Exclude<Parameter,'stage_dpi'|'active_stage'|'polling_rate'>;
export type ParameterCapability = { read:boolean; write:boolean; values:(number|boolean)[]; minimum:number|null; maximum:number|null; step:number|null };
export type PerformanceCapabilities = { snapshot_read:boolean; parameters:Record<Parameter,ParameterCapability> };
export type PerformanceSnapshot = {
  device_id:'pulsar_susanto_x'; firmware_version:string; active_profile_index:number; stage_count:number; active_stage_index:number;
  stages:{ index:number; x:number|null; y:number|null }[]; polling_rate_hz:number|null;
  sensor:{ lod:number|null; debounce:number|null; motion_sync:boolean|null; angle_snap:boolean|null; ripple_control:boolean|null; turbo:boolean|null; rotation:number|null; rotation_enabled:boolean|null };
  recorded_at:string;
};
export type PerformanceAction = { operation:'stage_dpi'; stage_index:number; dpi:number } | { operation:'active_stage'; stage_index:number }
  | { operation:'polling_rate'; hz:number } | { operation:'lod'; millimetres:number } | { operation:'debounce'; milliseconds:number }
  | { operation:'motion_sync'|'angle_snap'|'ripple_control'|'turbo'; enabled:boolean } | { operation:'rotation'; degrees:number };
export const record = (value:unknown):value is Record<string,unknown> => typeof value==='object' && value!==null && !Array.isArray(value);
const integer = (v:unknown,min:number,max:number):v is number => typeof v==='number' && Number.isInteger(v) && v>=min && v<=max;
const nullableInteger = (v:unknown,min:number,max:number) => v===null || integer(v,min,max);

export function isPerformanceCapabilities(value:unknown):value is PerformanceCapabilities {
  if (!record(value) || typeof value.snapshot_read!=='boolean' || !record(value.parameters)) return false;
  const parameters=value.parameters;
  return PARAMETERS.every(key => {
    const item=parameters[key];
    return record(item) && typeof item.read==='boolean' && typeof item.write==='boolean'
      && Array.isArray(item.values) && item.values.length<=32 && item.values.every(v=>typeof v==='boolean' || (typeof v==='number' && Number.isFinite(v)))
      && nullableInteger(item.minimum,-32000,32000) && nullableInteger(item.maximum,-32000,32000) && nullableInteger(item.step,1,32000)
      && (item.minimum===null || item.maximum===null || Number(item.minimum)<=Number(item.maximum));
  });
}

export function parseSnapshot(value:unknown):PerformanceSnapshot {
  if (record(value) && value.device_id==='pulsar_susanto_x' && typeof value.firmware_version==='string' && /^\d+\.[0-9a-f]{2}$/.test(value.firmware_version)
    && integer(value.active_profile_index,0,3) && integer(value.stage_count,1,6) && integer(value.active_stage_index,0,value.stage_count-1)
    && Array.isArray(value.stages) && value.stages.length===value.stage_count
    && value.stages.every((s,i)=>record(s) && s.index===i && nullableInteger(s.x,10,32000) && nullableInteger(s.y,10,32000))
    && (value.polling_rate_hz===null || [125,250,500,1000,2000,4000,8000].includes(Number(value.polling_rate_hz)) && typeof value.polling_rate_hz==='number')
    && record(value.sensor) && (value.sensor.lod===null || [0.7,1,2].includes(Number(value.sensor.lod)) && typeof value.sensor.lod==='number')
    && nullableInteger(value.sensor.debounce,0,15) && nullableInteger(value.sensor.rotation,-30,30)
    && (value.sensor.rotation_enabled===null || typeof value.sensor.rotation_enabled==='boolean')
    && ['motion_sync','angle_snap','ripple_control','turbo'].every(key=>value.sensor && record(value.sensor) && (value.sensor[key]===null || typeof value.sensor[key]==='boolean'))
    && typeof value.recorded_at==='string' && /^\d{4}-\d{2}-\d{2}T/.test(value.recorded_at) && Number.isFinite(Date.parse(value.recorded_at))) return value as PerformanceSnapshot;
  throw new Error('No valid Pulsar performance snapshot was received.');
}

export function actionValue(action:PerformanceAction):number|boolean {
  if (action.operation==='stage_dpi') return action.dpi;
  if (action.operation==='active_stage') return action.stage_index;
  if (action.operation==='polling_rate') return action.hz;
  if (action.operation==='lod') return action.millimetres;
  if (action.operation==='debounce') return action.milliseconds;
  if (action.operation==='rotation') return action.degrees;
  return action.enabled;
}

export function supportedAction(caps:PerformanceCapabilities|null|undefined,action:PerformanceAction,snapshot:PerformanceSnapshot|null):boolean {
  const cap=caps?.parameters[action.operation];
  if (!cap?.write || !snapshot) return false;
  if ((action.operation==='stage_dpi' || action.operation==='active_stage') && (!Number.isInteger(action.stage_index) || action.stage_index<0 || action.stage_index>=snapshot.stage_count)) return false;
  if (action.operation==='stage_dpi') {
    const dpi=action.dpi;
    const step=dpi<=10240?10:dpi<=25600?50:100;
    if (!Number.isInteger(dpi) || dpi<10 || dpi>32000 || dpi%step!==0) return false;
    const stage=snapshot.stages[action.stage_index];
    if (stage.x===null || stage.y===null) return false;
  } else if (action.operation!=='active_stage' && action.operation!=='polling_rate' && snapshot.sensor[action.operation]===null) return false;
  const value=actionValue(action);
  if (cap.values.length) return cap.values.includes(value);
  return typeof value==='number' && Number.isFinite(value) && cap.minimum!==null && cap.maximum!==null && value>=cap.minimum && value<=cap.maximum
    && (cap.step===null || (value-cap.minimum)%cap.step===0);
}

export function matchesAction(snapshot:PerformanceSnapshot,action:PerformanceAction):boolean {
  if (action.operation==='stage_dpi') { const stage=snapshot.stages[action.stage_index]; return stage?.x===action.dpi && stage?.y===action.dpi; }
  if (action.operation==='active_stage') return snapshot.active_stage_index===action.stage_index;
  if (action.operation==='polling_rate') return snapshot.polling_rate_hz===action.hz;
  return snapshot.sensor[action.operation]===actionValue(action) && (action.operation!=='rotation' || snapshot.sensor.rotation_enabled===true);
}

export function preservesOtherSettings(before:PerformanceSnapshot,after:PerformanceSnapshot,action:PerformanceAction):boolean {
  return before.firmware_version===after.firmware_version && before.active_profile_index===after.active_profile_index && before.stage_count===after.stage_count
    && (action.operation==='active_stage' || before.active_stage_index===after.active_stage_index)
    && (action.operation==='polling_rate' || before.polling_rate_hz===after.polling_rate_hz)
    && before.stages.every((s,i)=>action.operation==='stage_dpi' && i===action.stage_index || s.x===after.stages[i]?.x && s.y===after.stages[i]?.y)
    && (Object.keys(before.sensor) as (keyof PerformanceSnapshot['sensor'])[]).every(key=>key===action.operation || key==='rotation_enabled' && action.operation==='rotation' || before.sensor[key]===after.sensor[key]);
}

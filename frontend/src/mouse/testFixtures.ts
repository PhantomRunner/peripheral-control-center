import { PARAMETERS,type PerformanceCapabilities,type PerformanceSnapshot } from './performance';
export const performanceSnapshot:PerformanceSnapshot={device_id:'pulsar_susanto_x',firmware_version:'3.03',active_profile_index:0,stage_count:1,active_stage_index:0,
  stages:[{index:0,x:800,y:800}],polling_rate_hz:1000,sensor:{lod:1,debounce:5,motion_sync:false,angle_snap:false,ripple_control:false,turbo:false,rotation:0,rotation_enabled:false},recorded_at:'2026-10-24T20:00:00Z'};
export const performanceCaps:PerformanceCapabilities={snapshot_read:true,parameters:Object.fromEntries(PARAMETERS.map(key=>[key,{read:true,write:true,
  values:key==='stage_dpi'?[800,1200]:key==='polling_rate'?[500,1000]:['motion_sync','angle_snap','ripple_control','turbo'].includes(key)?[false,true]:[],
  minimum:key==='rotation'?-30:0,maximum:key==='rotation'?30:15,step:1}])) as PerformanceCapabilities['parameters']};

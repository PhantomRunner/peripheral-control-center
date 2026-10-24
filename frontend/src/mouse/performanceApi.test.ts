import { expect,it,vi } from 'vitest';
import { PerformanceClient } from './performanceApi';
import { parseSnapshot,supportedAction } from './performance';
import { performanceSnapshot,performanceCaps } from './testFixtures';

it('parses asymmetric readings and rejects missing, coerced or inconsistent state',()=>{
  expect(parseSnapshot({...performanceSnapshot,stages:[{index:0,x:800,y:1200}]}).stages[0].y).toBe(1200);
  for (const patch of [{stages:[]},{active_stage_index:1},{sensor:{...performanceSnapshot.sensor,rotation:'0'}},{polling_rate_hz:'1000'}]) expect(()=>parseSnapshot({...performanceSnapshot,...patch})).toThrow();
});

it('gates writes by evidence and bounds, never by receiver presence',()=>{
  const action={operation:'stage_dpi' as const,stage_index:0,dpi:800};
  expect(supportedAction(null,action,performanceSnapshot)).toBe(false);
  expect(supportedAction(performanceCaps,action,null)).toBe(false);
  expect(supportedAction(performanceCaps,action,performanceSnapshot)).toBe(true);
  expect(supportedAction(performanceCaps,{...action,dpi:801},performanceSnapshot)).toBe(false);
  expect(supportedAction(performanceCaps,{...action,stage_index:1},performanceSnapshot)).toBe(false);
});

it('sends one semantic action with the observed context and checks matching readback',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(Response.json({token:'a'.repeat(43),expires_in_seconds:1800}))
    .mockResolvedValueOnce(Response.json({status:'verified',requested:{operation:'stage_dpi',stage_index:0,dpi:800},actual:performanceSnapshot,persistence_verified:false,may_persist:true}));
  vi.stubGlobal('fetch',fetch);
  await new PerformanceClient().apply({operation:'stage_dpi',stage_index:0,dpi:800},performanceSnapshot);
  expect(fetch.mock.calls[1][0]).toBe('/api/devices/pulsar_susanto_x/performance/apply');
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({action:{operation:'stage_dpi',stage_index:0,dpi:800},expected_profile_index:0,expected_active_stage_index:0,vendor_tools_closed:true,allow_device_memory_writes:true});
});

it('does not retry uncertain writes or expose server diagnostics',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(Response.json({token:'a'.repeat(43),expires_in_seconds:1800})).mockResolvedValueOnce(new Response('/private/serial',{status:502}));
  vi.stubGlobal('fetch',fetch);
  await expect(new PerformanceClient().apply({operation:'polling_rate',hz:500},performanceSnapshot)).rejects.toThrow('not confirmed');
  expect(fetch).toHaveBeenCalledTimes(2);
});

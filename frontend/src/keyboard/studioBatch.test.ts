import { expect,it,vi } from 'vitest';
import { runStudioBatch } from './studioBatch';
import { DEFAULT_PROFILE } from './studioProfile';
import type { StudioIntent } from './studioApi';

it('sends clock then lighting and only then starts the accepted screen job',async()=>{
  const steps:string[]=[],client={apply:vi.fn(async (intent:StudioIntent,_tools:boolean,_memory:boolean)=>{steps.push(intent.operation);})},upload=vi.fn(async()=>{steps.push('screen');return true;});
  const frames=[{rgb565:new Uint8Array(32768),rgba:new Uint8ClampedArray(),delayMs:0}];
  expect(await runStudioBatch(DEFAULT_PROFILE,frames,client,upload,()=>true)).toBe('screen_started');
  expect(steps).toEqual(['clock','lighting','screen']);
  expect(client.apply.mock.calls.every(call=>call[1]===true&&call[2]===true)).toBe(true);
});
it.each([1,2])('stops after failure at control step %s and never sends later stages',async failing=>{
  const client={apply:vi.fn().mockImplementation(async()=>{if(client.apply.mock.calls.length===failing)throw new Error('private');})};
  const upload=vi.fn();
  await expect(runStudioBatch(DEFAULT_PROFILE,[{} as never],client,upload,()=>true)).rejects.toThrow('Earlier changes may remain');
  expect(client.apply).toHaveBeenCalledTimes(failing);expect(upload).not.toHaveBeenCalled();
});
it('does not queue a later write after loss of authorization or silently accept failed upload',async()=>{
  let active=true;const client={apply:vi.fn(async()=>{active=false;})},upload=vi.fn();
  await expect(runStudioBatch(DEFAULT_PROFILE,[],client,upload,()=>active)).rejects.toThrow('lighting');
  expect(client.apply).toHaveBeenCalledOnce();
  const ready={apply:vi.fn().mockResolvedValue(undefined)};
  await expect(runStudioBatch(DEFAULT_PROFILE,[{} as never],ready,async()=>false,()=>true)).rejects.toThrow('screen');
});

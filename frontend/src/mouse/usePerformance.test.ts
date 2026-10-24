import { act,renderHook } from '@testing-library/react';
import { expect,it,vi } from 'vitest';
import { mouse } from '../test/fixtures';
import { performanceCaps,performanceSnapshot } from './testFixtures';
import { usePerformance } from './usePerformance';

it('invalidates a pending snapshot when another settings operation clears observations',async()=>{
  let finish!:(value:Response)=>void;
  const fetch=vi.fn().mockResolvedValueOnce(Response.json({token:'a'.repeat(43),expires_in_seconds:1800})).mockReturnValueOnce(new Promise<Response>(resolve=>{finish=resolve;}));
  vi.stubGlobal('fetch',fetch);
  const device={...mouse,performance_capabilities:performanceCaps};
  const {result}=renderHook(()=>usePerformance(device,false,vi.fn()));
  let request!:Promise<void>;
  await act(async()=>{request=result.current.run();});
  const before=result.current.context;
  act(()=>{result.current.clear();});
  await act(async()=>{finish(Response.json(performanceSnapshot));await request;});
  expect(result.current.snapshot).toBeNull();
  expect(result.current.message).toBeNull();
  expect(result.current.context).not.toBe(before);
  expect(fetch).toHaveBeenCalledTimes(2);
});

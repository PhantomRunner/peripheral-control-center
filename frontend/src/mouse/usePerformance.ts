import { useEffect,useMemo,useRef,useState } from 'react';
import { hardwareContext } from '../hardwareContext';
import type { Device } from '../types';
import { PerformanceClient } from './performanceApi';
import { supportedAction,type PerformanceAction,type PerformanceSnapshot } from './performance';

export function usePerformance(device:Device,stale:boolean,onUpdated:()=>Promise<void>) {
  const [snapshot,setSnapshot]=useState<PerformanceSnapshot|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState<{error:boolean;text:string}|null>(null);
  const client=useMemo(()=>new PerformanceClient(),[]);
  const mounted=useRef(true), running=useRef(false);
  const context=hardwareContext(device,stale);
  const current=useRef({context,generation:0});
  if(current.current.context!==context) current.current={context,generation:current.current.generation+1};
  const generation=current.current.generation;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{setSnapshot(null);setMessage(null);},[context]);
  const available=!stale && device.status==='receiver_detected' && device.connection.receiver_usb_present;
  const readEnabled=available && device.performance_capabilities?.snapshot_read===true;
  const run=async(action?:PerformanceAction)=>{
    if(running.current || !readEnabled || (action && !supportedAction(device.performance_capabilities,action,snapshot))) return;
    running.current=true;setBusy(true);setMessage(null);
    try {
      const next=action && snapshot?await client.apply(action,snapshot):await client.read();
      if(mounted.current && current.current.generation===generation){setSnapshot(next);setMessage({error:false,text:action?'Setting applied and verified by device readback. Reconnect persistence remains unverified.':'Current stages and sensor settings read. Values describe this observation.'});}
    }catch(cause){if(mounted.current && current.current.generation===generation){setSnapshot(null);setMessage({error:true,text:cause instanceof Error?cause.message:'Performance operation was not confirmed.'});}}
    finally{running.current=false;if(mounted.current){setBusy(false);await onUpdated();}}
  };
  return {snapshot,busy,message,readEnabled,run,clear:()=>{setSnapshot(null);setMessage(null);},context};
}
export type PerformanceState=ReturnType<typeof usePerformance>;

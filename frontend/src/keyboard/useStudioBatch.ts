import { useEffect, useMemo, useRef, useState } from 'react';
import type { Device } from '../types';
import { hardwareContext } from '../hardwareContext';
import { compileScreen, type ScreenSource } from './screenMedia';
import type { StudioProfile } from './studioProfile';
import type { ScreenTransfer } from './ScreenUploadControls';
import { StudioClient } from './studioApi';
import { runStudioBatch } from './studioBatch';

export function useStudioBatch(device: Device, stale: boolean, profile: StudioProfile, source: ScreenSource | null, transfer: ScreenTransfer) {
  const [busy,setBusy]=useState(false),[message,setMessage]=useState<{error:boolean;text:string}|null>(null);
  const client=useMemo(()=>new StudioClient(),[]),alive=useRef(true),inFlight=useRef(false);
  const context=hardwareContext(device,stale),current=useRef({context,generation:0});
  if(current.current.context!==context)current.current={context,generation:current.current.generation+1};
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const profileKey=JSON.stringify(profile);
  useEffect(()=>{setMessage(null);},[context,profileKey,source]);
  const available=!stale&&device.status==='wired_detected'&&device.connection.wired_usb_present
    &&device.studio_capabilities?.clock_write===true&&device.studio_capabilities?.lighting_effects===true
    &&(!source||device.studio_capabilities?.screen_write===true)&&!transfer.busy;
  const run=async()=>{
    if(!available||inFlight.current)return;
    const generation=current.current.generation;
    inFlight.current=true;setBusy(true);setMessage(null);
    try{
      // Finish all media preparation before the first hardware request.
      const frames=source?compileScreen(source,profile.screen):[];
      const result=await runStudioBatch(profile,frames,client,transfer.start,()=>alive.current&&generation===current.current.generation);
      if(alive.current&&generation===current.current.generation)setMessage({error:false,text:result==='screen_started'
        ?'Clock and lighting commands acknowledged. Screen transfer started; follow its result on Screen. Actual state and persistence remain unverified.'
        :'Clock and lighting commands acknowledged. No screen artwork was loaded. Actual state and persistence remain unverified.'});
    }catch(cause){if(alive.current&&generation===current.current.generation)setMessage({error:true,text:cause instanceof Error?cause.message:'Sequence could not be completed.'});}
    finally{inFlight.current=false;if(alive.current)setBusy(false);}
  };
  return{busy,message,available,run};
}

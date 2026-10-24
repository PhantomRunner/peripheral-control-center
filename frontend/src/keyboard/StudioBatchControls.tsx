import { useEffect,useState } from 'react';
import type { StudioProfile } from './studioProfile';
import type { useStudioBatch } from './useStudioBatch';

export type StudioBatch=ReturnType<typeof useStudioBatch>;
export function StudioBatchControls({batch,profile,busy,hasArtwork}:{batch:StudioBatch;profile:StudioProfile;busy:boolean;hasArtwork:boolean}){
  const[toolsClosed,setToolsClosed]=useState(false),[memoryAllowed,setMemoryAllowed]=useState(false);
  const profileKey=JSON.stringify(profile);
  useEffect(()=>{setToolsClosed(false);setMemoryAllowed(false);},[profileKey,batch.available]);
  const run=async()=>{if(!batch.available||busy||batch.busy||!toolsClosed||!memoryAllowed)return;setToolsClosed(false);setMemoryAllowed(false);await batch.run();};
  return <div className="apply-controls" role="group" aria-label="Send everything">
    <h3>Send everything</h3><p className="device-note">Clock → lighting{hasArtwork?' → loaded screen artwork':''}. Stops at the first failed step; earlier changes may remain.</p>
    <label className="tool-confirmation"><input type="checkbox" checked={toolsClosed} disabled={!batch.available||busy||batch.busy} onChange={event=>setToolsClosed(event.target.checked)} />Other device-control tools are closed for Send everything</label>
    <label className="tool-confirmation"><input type="checkbox" checked={memoryAllowed} disabled={!batch.available||busy||batch.busy} onChange={event=>setMemoryAllowed(event.target.checked)} />Allow clock, lighting and loaded screen writes to device memory</label>
    <button className="refresh" type="button" disabled={!batch.available||busy||batch.busy||!toolsClosed||!memoryAllowed} onClick={()=>{void run();}}>Send everything</button>
    {batch.message&&<p role={batch.message.error?'alert':'status'} className={batch.message.error?'error':'profile-notice'}>{batch.message.text}</p>}
  </div>;
}

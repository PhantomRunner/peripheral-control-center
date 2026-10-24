import { useEffect, useMemo, useRef, useState } from 'react';
import type { Device } from '../types';
import { hardwareContext } from '../hardwareContext';
import { localClockTime, StudioClient } from './studioApi';

export function AutoClockControls({ device, stale, intervalMinutes, busy, onBusy, onUpdated }: {
  device: Device; stale: boolean; intervalMinutes: number; busy: boolean; onBusy: (value: boolean) => void; onUpdated: () => Promise<void>;
}) {
  const [active, setActive] = useState(false), [toolsClosed, setToolsClosed] = useState(false), [memoryAllowed, setMemoryAllowed] = useState(false);
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden');
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const alive = useRef(true), generation = useRef(0), timer = useRef<number | null>(null), busyNow = useRef(busy);
  busyNow.current = busy;
  const client = useMemo(() => new StudioClient(), []);
  const context = JSON.stringify([hardwareContext(device, stale), intervalMinutes]);
  const available = !stale && device.status === 'wired_detected' && device.connection.wired_usb_present && device.studio_capabilities?.clock_write === true;
  const stop = () => {
    generation.current += 1;
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null; setActive(false); setToolsClosed(false); setMemoryAllowed(false);
  };
  useEffect(() => {
    alive.current = true;
    const visibility = () => {
      const shown = document.visibilityState !== 'hidden'; setVisible(shown);
      if (!shown) { stop(); setMessage({ error:false,text:'Automatic sync stopped because the page is hidden.' }); }
    };
    document.addEventListener('visibilitychange',visibility);
    return () => { alive.current=false; generation.current+=1; if (timer.current!==null) window.clearTimeout(timer.current); document.removeEventListener('visibilitychange',visibility); };
  }, []);
  useEffect(() => { stop(); setMessage(null); }, [context]);
  const start = () => {
    if (!available || !visible || busy || !toolsClosed || !memoryAllowed || active || intervalMinutes < 1 || intervalMinutes > 1440) return;
    const run = ++generation.current;
    const interval = intervalMinutes * 60_000;
    setActive(true); setMessage({error:false,text:`Automatic clock sync enabled. First write in ${intervalMinutes} minute(s).`});
    const tick = async () => {
      timer.current = null;
      if (!alive.current || run!==generation.current) return;
      if (document.visibilityState==='hidden' || busyNow.current) { stop(); setMessage({error:false,text:'Automatic sync stopped because the page or keyboard is busy.'}); return; }
      onBusy(true);
      try {
        await client.apply({operation:'clock',local_time:localClockTime()},true,true);
        if (alive.current && run===generation.current) {
          setMessage({error:false,text:`Clock command acknowledged. Next write in at least ${intervalMinutes} minute(s); clock readback remains unavailable.`});
          timer.current=window.setTimeout(()=>{void tick();},interval);
        }
      } catch (cause) {
        if (alive.current && run===generation.current) { stop(); setMessage({error:true,text:`Automatic sync stopped. ${cause instanceof Error ? cause.message : 'Clock write was not confirmed.'}`}); }
      } finally { if (alive.current) { onBusy(false); await onUpdated(); } }
    };
    timer.current=window.setTimeout(()=>{void tick();},interval);
  };
  return <div className="apply-controls" role="group" aria-label="Automatic clock sync">
    <p className="device-note">Optional repeated writes every {intervalMinutes} minute(s), while Settings is open and visible. Errors stop sync. Keep other control tools closed until disabled.</p>
    <label className="tool-confirmation"><input type="checkbox" checked={toolsClosed} disabled={!available||!visible||active||busy} onChange={event=>setToolsClosed(event.target.checked)} />Other device-control tools stay closed for automatic clock sync</label>
    <label className="tool-confirmation"><input type="checkbox" checked={memoryAllowed} disabled={!available||!visible||active||busy} onChange={event=>setMemoryAllowed(event.target.checked)} />Allow repeated device-memory writes while automatic clock sync is enabled</label>
    <label className="tool-confirmation"><input type="checkbox" checked={active} disabled={!active && (!available || !visible || busy || !toolsClosed || !memoryAllowed)} onChange={event => {
      if (event.target.checked) start();
      else { stop(); setMessage({ error: false, text: 'Automatic clock sync stopped. An accepted bounded write may still finish.' }); }
    }} />Keep keyboard clock in sync</label>
    {message&&<p role={message.error?'alert':'status'} className={message.error?'error':'profile-notice'}>{message.text}</p>}
  </div>;
}

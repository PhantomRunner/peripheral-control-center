import { useEffect, useMemo, useRef, useState } from 'react';
import { hardwareContext } from '../hardwareContext';
import type { Device } from '../types';
import { StudioClient, type StudioIntent } from './studioApi';

export function StudioActionControls({ device, stale, supported, intent, label, busy = false, onBusy, onUpdated }: {
  device: Device; stale: boolean; supported: boolean; intent: StudioIntent | (() => StudioIntent); label: string;
  busy?: boolean; onBusy?: (value: boolean) => void; onUpdated: () => Promise<void>;
}) {
  const [toolsClosed, setToolsClosed] = useState(false), [memoryAllowed, setMemoryAllowed] = useState(false);
  const [pending, setPending] = useState(false), [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const client = useMemo(() => new StudioClient(), []);
  const alive = useRef(true);
  const context = JSON.stringify([hardwareContext(device, stale), supported, typeof intent === 'function' ? label : intent]);
  const current = useRef({ context, generation: 0 });
  if (current.current.context !== context) current.current = { context, generation: current.current.generation + 1 };
  const generation = current.current.generation;
  const available = supported && !stale && device.status === 'wired_detected' && device.connection.wired_usb_present;
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { setToolsClosed(false); setMemoryAllowed(false); setMessage(null); }, [context]);
  const apply = async () => {
    if (!available || busy || pending || !toolsClosed || !memoryAllowed) return;
    const requested = typeof intent === 'function' ? intent() : intent;
    setPending(true); onBusy?.(true); setMessage(null);
    try {
      await client.apply(requested, true, true);
      if (alive.current && generation === current.current.generation) setMessage({ error: false, text: `${requested.operation === 'lighting' ? 'Lighting' : requested.operation === 'clock' ? 'Clock' : 'Standby'} command acknowledged. Current settings and reconnect persistence remain unverified.` });
    } catch (cause) { if (alive.current && generation === current.current.generation) setMessage({ error: true, text: cause instanceof Error ? cause.message : 'Studio command was not confirmed.' }); }
    finally { if (alive.current) { setToolsClosed(false); setMemoryAllowed(false); setPending(false); onBusy?.(false); await onUpdated(); } }
  };
  return <div className="apply-controls">
    <label className="tool-confirmation"><input type="checkbox" checked={toolsClosed} disabled={!available || pending || busy} onChange={event => setToolsClosed(event.target.checked)} />Other device-control tools are closed for {label}</label>
    <label className="tool-confirmation"><input type="checkbox" checked={memoryAllowed} disabled={!available || pending || busy} onChange={event => setMemoryAllowed(event.target.checked)} />Allow device-memory writes for {label}</label>
    <button className="refresh" type="button" disabled={!available || pending || busy || !toolsClosed || !memoryAllowed} onClick={() => { void apply(); }}>{pending ? 'Sending…' : label}</button>
    <p className="device-note">{!supported ? 'This operation is unavailable in the current adapter.' : !available ? 'Connect by USB and restore the backend connection before sending.' : 'Writes may persist in device memory. Feedback confirms command acknowledgement; current settings are unavailable.'}</p>
    {message && <p role={message.error ? 'alert' : 'status'} className={message.error ? 'error' : 'profile-notice'}>{message.text}</p>}
  </div>;
}

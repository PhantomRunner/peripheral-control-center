import { useEffect, useMemo, useRef, useState } from 'react';
import { TelemetryClient } from '../telemetryApi';
import type { Device } from '../types';

export function KeyboardControl({ device, stale, onUpdated }: { device: Device; stale: boolean; onUpdated: () => Promise<void> }) {
  const [toolsClosed, setToolsClosed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const client = useMemo(() => new TelemetryClient(), []);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const available = device.connection.wired_usb_present && device.status === 'wired_detected' && !stale;
  const check = async () => {
    if (!available || busy || !toolsClosed) return;
    setBusy(true); setMessage(null);
    try {
      await client.readControl();
      if (mounted.current) setMessage({ error: false, text: 'The wired control interface responded.' });
    } catch (cause) {
      if (mounted.current) setMessage({ error: true, text: cause instanceof Error ? cause.message : 'Control response was not confirmed.' });
    } finally {
      if (mounted.current) { setToolsClosed(false); setBusy(false); await onUpdated(); }
    }
  };
  return <div className="telemetry-controls">
    <p className="device-note">Wired control: {device.control_responded === true ? 'Responded' : 'Not checked'}. Battery, firmware and current lighting remain unavailable.</p>
    {device.control_checked_at && <p className="device-note">Last control response: {new Date(device.control_checked_at).toLocaleString()}</p>}
    <label className="tool-confirmation"><input type="checkbox" checked={toolsClosed} disabled={!available || busy} onChange={(event) => setToolsClosed(event.target.checked)} />Other device-control tools are closed for control check</label>
    <button className="secondary" type="button" disabled={!available || busy || !toolsClosed} onClick={() => { void check(); }}>{busy ? 'Checking control…' : 'Check wired control'}</button>
    {message && <p role={message.error ? 'alert' : 'status'} className={message.error ? 'error' : 'profile-notice'}>{message.text}</p>}
  </div>;
}

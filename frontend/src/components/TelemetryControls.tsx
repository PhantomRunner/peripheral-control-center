import { useEffect, useMemo, useRef, useState } from 'react';
import { TelemetryClient } from '../telemetryApi';
import type { Device } from '../types';

export function TelemetryControls({ device, stale, onUpdated }: { device: Device; stale: boolean; onUpdated: () => Promise<void> }) {
  const [toolsClosed, setToolsClosed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const client = useMemo(() => new TelemetryClient(), []);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const available = device.status === 'receiver_detected' && device.connection.receiver_usb_present && !stale;

  const read = async (settings = false) => {
    const supported = settings ? device.capabilities.dpi_read && device.capabilities.polling_rate_read
      : device.capabilities.battery_read && device.capabilities.firmware_read;
    if (!available || !supported || !toolsClosed || busy) return;
    setBusy(true); setMessage(null);
    try {
      if (settings) await client.readSettings();
      else await client.read();
      if (mounted.current) setMessage({ error: false, text: settings ? 'DPI and stored polling read successfully.' : 'Battery and firmware read successfully.' });
    } catch (cause) {
      if (mounted.current) setMessage({ error: true, text: cause instanceof Error ? cause.message : 'Hardware read was not confirmed.' });
    } finally {
      if (mounted.current) {
        setToolsClosed(false); setBusy(false);
        await onUpdated();
      }
    }
  };

  return <div className="telemetry-controls">
    <label className="tool-confirmation"><input type="checkbox" checked={toolsClosed} disabled={busy || !available} onChange={(event) => setToolsClosed(event.target.checked)} />Other device-control tools are closed</label>
    {device.capabilities.battery_read && device.capabilities.firmware_read && <button className="secondary" type="button" disabled={busy || !available || !toolsClosed} onClick={() => { void read(); }}>{busy ? 'Reading hardware…' : 'Read battery and firmware'}</button>}
    {device.capabilities.dpi_read && device.capabilities.polling_rate_read && <button className="secondary" type="button" disabled={busy || !available || !toolsClosed} onClick={() => { void read(true); }}>Read DPI and polling</button>}
    {!available && <p className="device-note">Connect the receiver and restore the backend connection before reading.</p>}
    {message && <p role={message.error ? 'alert' : 'status'} className={message.error ? 'error' : 'profile-notice'}>{message.text}</p>}
  </div>;
}

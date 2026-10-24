import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { TelemetryClient } from '../telemetryApi';
import type { Device } from '../types';

export const BATTERY_INTERVAL_MS = 60_000;

export function BatteryPolling({ device, stale, onUpdated }: {
  device: Device; stale: boolean; onUpdated: () => Promise<void>;
}) {
  const [toolsClosed, setToolsClosed] = useState(false);
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden');
  const client = useMemo(() => new TelemetryClient(), []);
  const timer = useRef<number | null>(null);
  const generation = useRef(0);
  const mounted = useRef(true);
  const available = !stale && device.status === 'receiver_detected' && device.connection.receiver_usb_present
    && device.capabilities.battery_read && device.capabilities.firmware_read;

  const stop = useCallback(() => {
    generation.current += 1;
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
    setActive(false); setToolsClosed(false);
  }, []);

  useEffect(() => {
    mounted.current = true;
    const visibility = () => {
      const shown = document.visibilityState !== 'hidden';
      setVisible(shown);
      if (!shown) { stop(); setMessage({ error: false, text: 'Polling stopped because the page is hidden. Start it explicitly to resume.' }); }
    };
    document.addEventListener('visibilitychange', visibility);
    return () => {
      mounted.current = false;
      generation.current += 1;
      if (timer.current !== null) window.clearTimeout(timer.current);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [stop]);

  const start = () => {
    if (!available || !toolsClosed || !visible || busy || active) return;
    const run = ++generation.current;
    setActive(true); setToolsClosed(false);
    setMessage({ error: false, text: 'Polling enabled. The first read is in at least 60 seconds.' });
    const tick = async () => {
      timer.current = null;
      if (!mounted.current || generation.current !== run) return;
      if (document.visibilityState === 'hidden') { stop(); return; }
      setBusy(true);
      let succeeded = false;
      try {
        await client.read(true);
        succeeded = true;
      } catch (cause) {
        if (mounted.current && generation.current === run) {
          stop();
          setMessage({ error: true, text: `Polling stopped. ${cause instanceof Error ? cause.message : 'Hardware read was not confirmed.'}` });
        }
      } finally {
        if (mounted.current) {
          setBusy(false);
          await onUpdated();
          if (succeeded && mounted.current && generation.current === run) {
            setMessage({ error: false, text: 'Battery read confirmed. Next read in at least 60 seconds.' });
            timer.current = window.setTimeout(() => { void tick(); }, BATTERY_INTERVAL_MS);
          }
        }
      }
    };
    timer.current = window.setTimeout(() => { void tick(); }, BATTERY_INTERVAL_MS);
  };

  return <div className="telemetry-controls" role="group" aria-label="Battery polling">
    <p className="device-note">Optional battery/firmware polling: at least 60 seconds after each completed read, only while this device page is visible. Errors stop polling. Keep other device-control tools closed until stopped.</p>
    <label className="tool-confirmation"><input type="checkbox" checked={toolsClosed} disabled={!available || !visible || active || busy} onChange={(event) => setToolsClosed(event.target.checked)} />Other device-control tools stay closed while polling</label>
    <button className="secondary" type="button" disabled={!available || !visible || active || busy || !toolsClosed} onClick={start}>Start battery polling</button>
    <button className="secondary" type="button" disabled={!active} onClick={() => { stop(); setMessage({ error: false, text: 'Polling stopped. A read already in progress may still finish.' }); }}>Stop battery polling</button>
    {busy && <p className="device-note">Reading battery…</p>}
    {message && <p role={message.error ? 'alert' : 'status'} className={message.error ? 'error' : 'profile-notice'}>{message.text}</p>}
  </div>;
}

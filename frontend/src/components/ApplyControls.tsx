import { useEffect, useMemo, useRef, useState } from 'react';
import type { SettingsIntent } from '../profilesApi';
import { SettingsClient } from '../settingsApi';
import type { Device } from '../types';

export function ApplyControls({ device, desired, stale, busy, onBusy }: {
  device: Device; desired: SettingsIntent; stale: boolean; busy: boolean; onBusy: (value: boolean) => void;
}) {
  const [result, setResult] = useState<{ error: boolean; message: string } | null>(null);
  const client = useMemo(() => new SettingsClient(), []);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setResult(null); }, [desired, device.id]);
  const unavailable = !device.capabilities.settings_write || stale || device.status === 'offline';

  const apply = async () => {
    if (unavailable || busy) return;
    onBusy(true); setResult(null);
    try {
      await client.apply(device.id, desired);
      if (mounted.current) setResult({ error: false, message: 'Settings applied and verified by device readback.' });
    } catch (cause) {
      if (mounted.current) setResult({ error: true, message: cause instanceof Error ? cause.message : 'Settings could not be verified.' });
    } finally { if (mounted.current) onBusy(false); }
  };

  return <div className="apply-controls">
    <button className="refresh" type="button" disabled={unavailable || busy} onClick={() => { void apply(); }}>Apply settings</button>
    <p className="device-note">{!device.capabilities.settings_write ? 'Hardware Apply is unavailable until the adapter is validated for this device.'
      : stale ? 'Refresh the backend connection before applying settings.'
      : device.status === 'offline' ? 'Connect the device before applying settings.'
      : 'Only pressing Apply changes device settings. Saving or loading a profile does not apply it.'}</p>
    {result && <p className={result.error ? 'error' : 'profile-notice'} role={result.error ? 'alert' : 'status'}>{result.message}</p>}
  </div>;
}

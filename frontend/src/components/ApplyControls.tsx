import { useEffect, useMemo, useRef, useState } from 'react';
import type { SettingsIntent } from '../profilesApi';
import { SettingsClient } from '../settingsApi';
import type { Device } from '../types';

export function ApplyControls({ device, desired, stale, busy, onBusy, onUpdated }: {
  device: Device; desired: SettingsIntent; stale: boolean; busy: boolean; onBusy: (value: boolean) => void; onUpdated?: () => Promise<void>;
}) {
  const [result, setResult] = useState<{ error: boolean; message: string } | null>(null);
  const [toolsClosed, setToolsClosed] = useState(false);
  const [memoryAllowed, setMemoryAllowed] = useState(false);
  const client = useMemo(() => new SettingsClient(), []);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setResult(null); setToolsClosed(false); setMemoryAllowed(false); }, [desired, device.id]);
  const wiredRequired = device.kind === 'keyboard' && !device.connection.wired_usb_present;
  const options = device.write_options;
  const rgbOptions = device.rgb_write_options;
  const memoryRequired = options !== null || rgbOptions?.may_persist === true;
  const unsupported = desired.kind === 'mouse' && options !== null
    && ((desired.dpi !== null && !options.dpi.includes(desired.dpi))
      || (desired.polling_rate_hz !== null && !options.polling_rate_hz.includes(desired.polling_rate_hz)));
  const unsupportedRgb = desired.kind === 'keyboard' && rgbOptions !== null
    && !rgbOptions.brightness_steps.includes(desired.rgb.brightness_percent);
  const unavailable = !device.capabilities.settings_write || stale || device.status === 'offline' || wiredRequired || unsupported || unsupportedRgb;

  const apply = async () => {
    if (unavailable || busy || !toolsClosed || (memoryRequired && !memoryAllowed)) return;
    onBusy(true); setResult(null);
    try {
      const outcome = await client.apply(device.id, desired, true, memoryRequired && memoryAllowed);
      if (mounted.current) setResult({ error: false, message: 'status' in outcome && outcome.status === 'acknowledged'
        ? 'Lighting command acknowledged. Current RGB and reconnect persistence remain unverified.'
        : 'Settings applied and verified by device readback.' });
    } catch (cause) {
      if (mounted.current) setResult({ error: true, message: cause instanceof Error ? cause.message : 'Settings could not be verified.' });
    } finally { if (mounted.current) { setToolsClosed(false); setMemoryAllowed(false); onBusy(false); await onUpdated?.(); } }
  };

  return <div className="apply-controls">
    {device.capabilities.settings_write && <label className="tool-confirmation"><input type="checkbox" checked={toolsClosed} disabled={unavailable || busy} onChange={(event) => setToolsClosed(event.target.checked)} />Other device-control tools are closed for Apply</label>}
    {device.capabilities.settings_write && memoryRequired && <label className="tool-confirmation"><input type="checkbox" checked={memoryAllowed} disabled={unavailable || busy} onChange={(event) => setMemoryAllowed(event.target.checked)} />Allow settings writes that may persist in device memory</label>}
    <button className="refresh" type="button" disabled={unavailable || busy || !toolsClosed || (memoryRequired && !memoryAllowed)} onClick={() => { void apply(); }}>Apply settings</button>
    <p className="device-note">{!device.capabilities.settings_write ? 'Hardware Apply is unavailable until the adapter is validated for this device.'
      : stale ? 'Refresh the backend connection before applying settings.'
      : device.status === 'offline' ? 'Connect the device before applying settings.'
      : wiredRequired ? 'Connect the keyboard by USB before applying RGB settings.'
      : unsupported || unsupportedRgb ? 'The selected values are outside the verified settings listed below.'
      : 'Only pressing Apply changes device settings. Saving or loading a profile does not apply it.'}</p>
    {options && <p className="device-note">Verified writes: DPI {options.dpi.join(' / ')}; polling {options.polling_rate_hz.join(' / ')} Hz. Use firmware {options.firmware_version}, onboard profile {options.profile_index + 1}, DPI stage {options.active_stage_index + 1}. Settings may persist in device memory.</p>}
    {rgbOptions && <p className="device-note">Static RGB; brightness levels {rgbOptions.brightness_steps.join(' / ')}%. Device feedback confirms command acknowledgement. Current RGB and reconnect persistence remain unavailable.</p>}
    {result && <p className={result.error ? 'error' : 'profile-notice'} role={result.error ? 'alert' : 'status'}>{result.message}</p>}
  </div>;
}

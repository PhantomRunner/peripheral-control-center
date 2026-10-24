import { useEffect, useState } from 'react';
import { hardwareContext } from '../hardwareContext';
import type { Device } from '../types';
import type { ScreenFrame } from './screenMedia';
import type { useScreenTransfer } from './useScreenTransfer';

export type ScreenTransfer = ReturnType<typeof useScreenTransfer>;
export function ScreenUploadControls({ device, stale, frames, preparing, transfer }: { device: Device; stale: boolean; frames: ScreenFrame[]; preparing: boolean; transfer: ScreenTransfer }) {
  const [toolsClosed, setToolsClosed] = useState(false), [memoryAllowed, setMemoryAllowed] = useState(false);
  const context = hardwareContext(device, stale);
  useEffect(() => { setToolsClosed(false); setMemoryAllowed(false); }, [context, frames]);
  const supported = device.studio_capabilities?.screen_write === true;
  const available = supported && !stale && device.status === 'wired_detected' && device.connection.wired_usb_present
    && frames.length > 0 && frames.length <= (device.studio_capabilities?.max_screen_frames ?? 0) && !preparing && !transfer.busy;
  const start = async () => {
    if (!available || !toolsClosed || !memoryAllowed) return;
    setToolsClosed(false); setMemoryAllowed(false);
    await transfer.start(frames);
  };
  return <div className="apply-controls">
    <label className="tool-confirmation"><input type="checkbox" checked={toolsClosed} disabled={!available} onChange={event => setToolsClosed(event.target.checked)} />Other device-control tools are closed for screen upload</label>
    <label className="tool-confirmation"><input type="checkbox" checked={memoryAllowed} disabled={!available} onChange={event => setMemoryAllowed(event.target.checked)} />Allow replacing the TFT image and writing device memory</label>
    <button className="refresh" type="button" disabled={!available || !toolsClosed || !memoryAllowed} onClick={() => { void start(); }}>{transfer.busy ? 'Uploading screen…' : 'Send screen to keyboard'}</button>
    <p className="device-note">{!supported ? 'Screen transfer is unavailable in the current adapter. Preview/export remain local.' : 'Replaces the current screen artwork and may persist in device memory. Keep other control tools closed until finished. Leaving this tab does not cancel an accepted transfer.'}</p>
    {transfer.job && <p role="status" className="profile-notice">{transfer.job.status === 'running' ? `Transferring ${transfer.job.frame_count} frame(s), ${transfer.job.total_blocks} blocks. Allow up to 5 minutes.`
      : transfer.job.status === 'transfer_completed' ? 'Screen transfer completed with device receipts. Display readback and reconnect persistence remain unverified.' : 'Screen transfer was not confirmed. Artwork may have changed; check before retrying.'}</p>}
    {transfer.error && <p role="alert" className="error">{transfer.error}</p>}
    {transfer.error && transfer.job && <button className="secondary" type="button" onClick={() => { void transfer.refreshStatus(); }}>Refresh transfer status</button>}
  </div>;
}

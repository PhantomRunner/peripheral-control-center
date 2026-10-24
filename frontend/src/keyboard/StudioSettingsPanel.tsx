import { useEffect, useRef, useState } from 'react';
import { download } from './download';
import { exportStudioProfile, parseStudioProfile, type StudioProfile } from './studioProfile';
import type { Device } from '../types';
import { StudioActionControls } from './StudioActionControls';
import { localClockTime } from './studioApi';
import { AutoClockControls } from './AutoClockControls';
import { StudioBatchControls,type StudioBatch } from './StudioBatchControls';

export function StudioSettingsPanel({ profile, onChange, device, stale, onUpdated, externalBusy=false,batch,hasArtwork=false }: { profile: StudioProfile; onChange: (value: StudioProfile) => void; device: Device; stale: boolean; onUpdated: () => Promise<void>; externalBusy?:boolean;batch?:StudioBatch;hasArtwork?:boolean }) {
  const [notice, setNotice] = useState<{ error: boolean; text: string } | null>(null);
  const [clock, setClock] = useState(() => new Date());
  const [loading, setLoading] = useState(false);
  const [localBusy, setBusy] = useState(false);
  const busy=localBusy||externalBusy;
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  // No HID operation, session consent or automatic-sync timer is stored in a profile.
  const load = async (file?: File) => {
    if (!file) return;
    if (file.size > 65_536) { setNotice({ error: true, text: 'Profile exceeds 64 KiB.' }); return; }
    setLoading(true);
    try {
      const value = parseStudioProfile(await file.text());
      if (mounted.current) { onChange(value); setNotice({ error: false, text: 'Local Studio profile loaded. No device settings changed; media files and automatic sync are not loaded.' }); }
    } catch (cause) { if (mounted.current) setNotice({ error: true, text: cause instanceof Error ? cause.message : 'Could not load this profile.' }); }
    finally { if (mounted.current) setLoading(false); }
  };
  return <div className="studio-screen-grid">
    <section className="panel studio-form" aria-labelledby="studio-standby-title">
      <div className="studio-kicker">DEVICE / DRAFT</div><h2 id="studio-standby-title">Standby & clock</h2>
      <label>Screen standby<select disabled={busy} value={profile.standbyMinutes} onChange={event => onChange({ ...profile, standbyMinutes: Number(event.target.value) })}>{[[0,'Never'],[1,'1 minute'],[5,'5 minutes'],[30,'30 minutes']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <StudioActionControls device={device} stale={stale} supported={device.studio_capabilities?.standby_write === true} intent={{ operation: 'standby', minutes: profile.standbyMinutes }} label="Apply standby" busy={busy} onBusy={setBusy} onUpdated={onUpdated} />
      <p className="device-note">Four configured standby choices. The current keyboard setting is unavailable.</p>
      <div className="studio-clock"><span>COMPUTER LOCAL TIME</span><strong>{clock.toLocaleTimeString()}</strong><small>{clock.toLocaleDateString()} · {Intl.DateTimeFormat().resolvedOptions().timeZone}</small></div>
      <button className="studio-text-button" type="button" onClick={() => setClock(new Date())}>Refresh clock preview</button>
      <StudioActionControls device={device} stale={stale} supported={device.studio_capabilities?.clock_write === true} intent={() => ({ operation: 'clock', local_time: localClockTime() })} label="Sync keyboard clock" busy={busy} onBusy={setBusy} onUpdated={onUpdated} />
      <label>Automatic sync interval (minutes)<input type="number" min="1" max="1440" value={profile.clockIntervalMinutes} onChange={event => onChange({ ...profile, clockIntervalMinutes: Math.max(1, Math.min(1440, Math.round(Number(event.target.value)))) })} /></label>
      <AutoClockControls device={device} stale={stale} intervalMinutes={profile.clockIntervalMinutes} busy={busy} onBusy={setBusy} onUpdated={onUpdated} />
    </section>
    <section className="panel studio-form" aria-labelledby="studio-profile-title">
      <div className="studio-kicker">LOCAL / PORTABLE</div><h2 id="studio-profile-title">Studio profile</h2>
      <p className="device-note">Keep lighting, standby, clock interval, text/crop options, preview layout and Linux mappings in a JSON file. Images, GIFs and hardware confirmations are not included.</p>
      <button className="refresh" type="button" onClick={() => download('pcc-ak820-studio.json', exportStudioProfile(profile), 'application/json')}>Export Studio profile</button>
      <label>Import Studio profile<input type="file" accept="application/json,.json" disabled={loading||busy} onChange={event => { void load(event.target.files?.[0]); event.target.value = ''; }} /></label>
      <p className="device-note">Accepts PCC Studio profiles and original AK820 Pro Studio version 1 exports. Import replaces local drafts and never sends them to the keyboard.</p>
      {notice && <p role={notice.error ? 'alert' : 'status'} className={notice.error ? 'error' : 'profile-notice'}>{notice.text}</p>}
      <div className="studio-feature-list"><div><span>Lighting</span><strong>{profile.lighting.effect.replaceAll('_', ' ')}</strong></div><div><span>Colour / brightness</span><strong>{profile.lighting.color} / {profile.lighting.brightness}%</strong></div><div><span>Linux mappings</span><strong>{profile.mappings.length}</strong></div><div><span>Media files</span><strong>Not included</strong></div></div>
      <p className="device-note">For the existing backend-managed static RGB profiles, open Device & profiles. Both forms store desired settings; neither is a hardware backup.</p>
      <a className="detail-link" href="/third-party-notices.txt" target="_blank" rel="noreferrer">Third-party licenses ↗</a>
      {batch&&<StudioBatchControls batch={batch} profile={profile} busy={localBusy||externalBusy&&!batch.busy} hasArtwork={hasArtwork} />}
    </section>
  </div>;
}

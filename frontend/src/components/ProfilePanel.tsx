import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ProfileClient, type ProfileDraft, type SettingsIntent, type SoftwareProfile } from '../profilesApi';
import type { Device } from '../types';
import { ApplyControls } from './ApplyControls';

function initialSettings(kind: Device['kind']): SettingsIntent {
  return kind === 'mouse' ? { kind: 'mouse', dpi: 800, polling_rate_hz: 1000 }
    : { kind: 'keyboard', rgb: { mode: 'static', color: '#7766ff', brightness_percent: 50 } };
}

export function ProfilePanel({ device, stale = false }: { device: Device; stale?: boolean }) {
  const [open, setOpen] = useState(false);
  const [profiles, setProfiles] = useState<SoftwareProfile[]>([]);
  const [selected, setSelected] = useState<SoftwareProfile | null>(null);
  const [name, setName] = useState('New profile');
  const [settings, setSettings] = useState<SettingsIntent>(() => initialSettings(device.kind));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const client = useMemo(() => new ProfileClient(), []);
  const alive = useRef(true);
  const panelId = useId();

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setBusy(true);
    client.list(controller.signal).then((items) => {
      if (!controller.signal.aborted) { setProfiles(items); setError(null); }
    }).catch((cause) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Cannot load profiles.');
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [open, client]);

  const load = (value: SoftwareProfile | null) => {
    setSelected(value);
    setName(value?.name ?? 'New profile');
    setSettings(value?.settings ?? initialSettings(device.kind));
    setNotice(value ? 'Profile loaded into the draft. No device settings changed.' : null);
    setError(null);
  };

  const reload = async () => {
    setBusy(true); setError(null);
    try {
      const items = await client.list();
      if (alive.current) { setProfiles(items); load(null); }
    } catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Cannot load profiles.'); }
    finally { if (alive.current) setBusy(false); }
  };

  const save = async (asNew: boolean) => {
    setBusy(true); setError(null); setNotice(null);
    const draft: ProfileDraft = { name: name.trim(), device_id: device.id as ProfileDraft['device_id'], settings };
    try {
      const saved = await client.save(draft, asNew ? null : selected);
      if (alive.current) {
        setProfiles((items) => [...items.filter((item) => item.id !== saved.id), saved]);
        setSelected(saved); setName(saved.name);
        setNotice('Profile saved locally. No device settings changed.');
      }
    } catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Cannot save profile.'); }
    finally { if (alive.current) setBusy(false); }
  };

  const remove = async () => {
    if (!selected) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      await client.remove(selected);
      if (alive.current) { setProfiles((items) => items.filter((item) => item.id !== selected.id)); load(null); setNotice('Local profile deleted. Device settings were not changed.'); }
    } catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Cannot delete profile.'); }
    finally { if (alive.current) setBusy(false); }
  };

  const empty = settings.kind === 'mouse' && settings.dpi === null && settings.polling_rate_hz === null;
  return (
    <section className="panel profile-panel" aria-label="Software profiles">
      <div className="panel-heading"><h2>Software profiles</h2><button className="secondary" type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)} disabled={busy}>{open ? 'Close profiles' : 'Manage profiles'}</button></div>
      <p className="device-note">Save desired settings locally. Loading or saving a profile never applies it to the device.</p>
      {open && <div id={panelId}>
        {error && <p role="alert" className="error">{error}</p>}
        {notice && <p role="status" className="profile-notice">{notice}</p>}
        <div className="profile-toolbar"><label>Saved profile<select disabled={busy} value={selected?.id ?? ''} onChange={(event) => load(profiles.find((item) => item.id === event.target.value) ?? null)}><option value="">New draft</option>{profiles.filter((item) => item.device_id === device.id).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><button type="button" className="secondary" disabled={busy} onClick={() => { void reload(); }}>Reload profiles</button></div>
        <form onSubmit={(event) => { event.preventDefault(); void save(false); }}>
          <fieldset disabled={busy} className="profile-fields"><legend>Desired settings · local draft</legend>
            <label>Profile name<input required maxLength={64} value={name} onChange={(event) => setName(event.target.value)} /></label>
            {settings.kind === 'mouse' ? <>
              <label>DPI (draft)<input type="number" min={1} max={32000} step={1} placeholder="Leave unchanged" value={settings.dpi ?? ''} onChange={(event) => setSettings({ ...settings, dpi: event.target.value === '' ? null : Number(event.target.value) })} /></label>
              <label>Polling rate (draft)<select value={settings.polling_rate_hz ?? ''} onChange={(event) => setSettings({ ...settings, polling_rate_hz: event.target.value === '' ? null : Number(event.target.value) })}><option value="">Leave unchanged</option>{[125, 250, 500, 1000, 2000, 4000, 8000].map((rate) => <option key={rate} value={rate}>{rate} Hz</option>)}</select></label>
            </> : <>
              <label>Static RGB color (draft)<input type="color" value={settings.rgb.color} onChange={(event) => setSettings({ ...settings, rgb: { ...settings.rgb, color: event.target.value } })} /></label>
              <label>Brightness percent (draft)<input type="number" required min={0} max={100} step={1} value={settings.rgb.brightness_percent} onChange={(event) => setSettings({ ...settings, rgb: { ...settings.rgb, brightness_percent: Number(event.target.value) } })} /></label>
            </>}
          </fieldset>
          <div className="profile-actions"><button className="refresh" type="submit" disabled={busy || !name.trim() || empty}>{busy ? 'Working…' : selected ? 'Save changes locally' : 'Save profile locally'}</button>{selected && <><button className="secondary" type="button" disabled={busy || !name.trim() || empty} onClick={() => { void save(true); }}>Save as new profile</button><button className="secondary danger" type="button" disabled={busy} onClick={() => { void remove(); }}>Delete local profile</button></>}</div>
        </form>
        <ApplyControls device={device} desired={settings} stale={stale} busy={busy || empty} onBusy={setBusy} />
        <p className="device-note">Saved values are desired settings, not hardware readings.</p>
      </div>}
    </section>
  );
}

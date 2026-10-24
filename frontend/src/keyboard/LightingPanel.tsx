import { useMemo, useState } from 'react';
import { ApplyControls } from '../components/ApplyControls';
import type { KeyboardSettings } from '../profilesApi';
import type { Device } from '../types';
import { KeyboardPreview } from './KeyboardPreview';
import { directional, EFFECTS, verifiedStatic, type LightingDraft } from './lighting';

export function LightingPanel({ device, stale, draft, onChange, iso, onIso, onUpdated }: {
  device: Device; stale: boolean; draft: LightingDraft; onChange: (value: LightingDraft) => void;
  iso: boolean; onIso: (value: boolean) => void; onUpdated: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const desired = useMemo<KeyboardSettings>(() => ({ kind: 'keyboard', rgb: { mode: 'static', color: draft.color, brightness_percent: draft.brightness } }), [draft.color, draft.brightness]);
  return <div className="studio-lighting-grid">
    <section className="panel studio-preview-panel" aria-label="Lighting preview">
      <div className="panel-heading"><div><div className="studio-kicker">AK820 PRO / LIGHTING</div><h2>Make it yours.</h2></div><span className="studio-badge">Preview only</span></div>
      <KeyboardPreview draft={draft} iso={iso} />
      <div className="studio-footnote"><span>75% layout · rotary knob · 128 × 128 TFT</span><label>Preview layout<select aria-label="Preview layout" value={iso ? 'iso' : 'ansi'} onChange={event => onIso(event.target.value === 'iso')}><option value="ansi">ANSI</option><option value="iso">ISO</option></select></label></div>
    </section>
    <section className="panel studio-form" aria-labelledby="lighting-controls-title">
      <div className="studio-kicker">CUSTOMIZE</div><h2 id="lighting-controls-title">Lighting</h2>
      <p className="device-note">Try an effect on the preview. Send supported settings only when you are ready.</p>
      <fieldset disabled={busy}><legend className="sr-only">Lighting draft</legend>
        <label>Effect<select value={draft.effect} onChange={event => onChange({ ...draft, effect: event.target.value as LightingDraft['effect'], ...(event.target.value === 'static' ? { speed: 0, direction: 'left', rainbow: false } : {}) })}>{EFFECTS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        <label className="studio-range">Brightness <output>{draft.brightness}%</output><input type="range" min="0" max="100" step="20" value={draft.brightness} onChange={event => onChange({ ...draft, brightness: Number(event.target.value) })} /></label>
        <div className="studio-two-fields"><label>Speed<select disabled={['static', 'off'].includes(draft.effect)} value={draft.speed} onChange={event => onChange({ ...draft, speed: Number(event.target.value) })}>{[0, 1, 2, 3, 4, 5].map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Direction<select disabled={!directional(draft.effect)} value={draft.direction} onChange={event => onChange({ ...draft, direction: event.target.value as LightingDraft['direction'] })}>{['left', 'down', 'up', 'right'].map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></label></div>
        <label>Colour<div className="studio-colour"><input aria-label="Lighting colour" type="color" value={draft.color} onChange={event => onChange({ ...draft, color: event.target.value })} /><span>{draft.color.toUpperCase()}</span></div></label>
        <div className="studio-swatches" aria-label="Colour presets">{['#4080ff', '#7766ff', '#ff5588', '#ffb347', '#67dfb0', '#ffffff'].map(color => <button key={color} type="button" aria-label={`Use colour ${color}`} style={{ backgroundColor: color }} aria-pressed={draft.color === color} onClick={() => onChange({ ...draft, color })} />)}</div>
        <label className="tool-confirmation"><input type="checkbox" checked={draft.rainbow} onChange={event => onChange({ ...draft, rainbow: event.target.checked })} />Rainbow — replaces the selected colour</label>
      </fieldset>
      <ApplyControls device={device} desired={desired} stale={stale} busy={busy} onBusy={setBusy} onUpdated={onUpdated}
        disabledReason={verifiedStatic(draft) ? undefined : 'This effect is available in the preview. Hardware Apply needs validation on this keyboard; select Static without Rainbow to use verified RGB.'} />
    </section>
  </div>;
}

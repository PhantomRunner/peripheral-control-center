import { useEffect, useRef, useState } from 'react';
import { compileScreen, loadScreenFile, screenPayload, textSource, type ScreenDraft, type ScreenFrame, type ScreenSource } from './screenMedia';
import { download } from './download';
import type { Device } from '../types';
import { ScreenUploadControls, type ScreenTransfer } from './ScreenUploadControls';

export function ScreenPanel({ draft, onChange, source, onSource, device, stale, transfer }: {
  draft: ScreenDraft; onChange: (value: ScreenDraft) => void; source: ScreenSource | null; onSource: (source: ScreenSource | null) => void;
  device: Device; stale: boolean; transfer: ScreenTransfer;
}) {
  const [frames, setFrames] = useState<ScreenFrame[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preview = useRef<HTMLCanvasElement>(null);
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);
  useEffect(() => {
    setFrames([]); setIndex(0); setPlaying(false);
    if (!source) return;
    setBusy(true);
    const timer = window.setTimeout(() => {
      try { setFrames(compileScreen(source, draft)); setError(null); }
      catch { setError('Could not convert this media to a screen frame.'); }
      finally { setBusy(false); }
    }, 200);
    return () => window.clearTimeout(timer);
  }, [source, draft.cropX, draft.cropY, draft.zoom, draft.dither, draft.maxFrames, draft.background]);
  useEffect(() => {
    const context = preview.current?.getContext('2d');
    context?.clearRect(0, 0, 128, 128);
    if (frames[index]) context?.putImageData(new ImageData(new Uint8ClampedArray(frames[index].rgba), 128, 128), 0, 0);
  }, [frames, index]);
  useEffect(() => {
    if (!playing || frames.length < 2) return;
    const visibility = () => { if (document.visibilityState === 'hidden') setPlaying(false); };
    document.addEventListener('visibilitychange', visibility);
    const delay = Math.max(20, Math.min(510, Math.round(frames[index].delayMs / 2) * 2));
    const timer = window.setTimeout(() => setIndex((index + 1) % frames.length), delay);
    return () => { window.clearTimeout(timer); document.removeEventListener('visibilitychange', visibility); };
  }, [playing, frames, index]);

  const load = async (file?: File) => {
    if (!file) return;
    const request = ++generation.current;
    setBusy(true); setError(null); setFrames([]); setPlaying(false);
    try {
      const decoded = await loadScreenFile(file);
      if (request === generation.current) onSource(decoded);
    } catch (cause) { if (request === generation.current) { onSource(null); setError(cause instanceof Error ? cause.message : 'Could not decode this image.'); } }
    finally { if (request === generation.current) setBusy(false); }
  };
  const renderText = () => {
    generation.current += 1;
    try { onSource(textSource(draft)); setError(null); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not render text.'); }
  };
  const clipped = frames.some(frame => frame.delayMs > 510 || frame.delayMs % 2 !== 0);
  return <div className="studio-screen-grid">
    <section className="panel studio-screen-preview" aria-label="Screen preview">
      <div className="panel-heading"><div><div className="studio-kicker">128 × 128 / RGB565</div><h2>A little canvas.</h2></div><span className="studio-badge">Local artwork</span></div>
      <div className="studio-display"><canvas ref={preview} width="128" height="128" aria-label="Converted TFT preview" /><span>{source ? source.name : 'Your artwork goes here'}</span></div>
      <p className="device-note">Preview uses the converted 16-bit pixels. It is not an image read from the keyboard.</p>
      {frames.length > 0 && <p className="studio-media-info">{frames.length} frame{frames.length !== 1 ? 's' : ''} · {(Math.ceil((256 + frames.length * 32768) / 4096) * 4096).toLocaleString()} bytes · frame {index + 1}</p>}
      {clipped && <p className="device-note">Device timing uses 2 ms steps and a maximum of 510 ms per frame. The preview uses those limits.</p>}
      <div className="profile-actions"><button className="secondary" type="button" disabled={frames.length < 2 || busy} onClick={() => setPlaying(!playing)}>{playing ? 'Pause animation' : 'Play animation'}</button><button className="secondary" type="button" disabled={!frames.length || busy} onClick={() => download('ak820-screen.rgb565', screenPayload(frames), 'application/octet-stream')}>Export screen data</button></div>
      <ScreenUploadControls device={device} stale={stale} frames={frames} preparing={busy} transfer={transfer} />
    </section>
    <section className="panel studio-form" aria-labelledby="screen-artwork-title">
      <div className="studio-kicker">CREATE</div><h2 id="screen-artwork-title">Screen artwork</h2>
      {error && <p role="alert" className="error">{error}</p>}
      <label>Choose an image or GIF<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" disabled={busy || transfer.busy} onChange={event => { void load(event.target.files?.[0]); event.target.value = ''; }} /></label>
      <p className="device-note">PNG, JPEG, WebP or GIF · up to 10 MiB / 120 frames. Files stay in this browser.</p>
      <fieldset disabled={busy || transfer.busy}>
        <legend>Or write text</legend><label>Text artwork<textarea maxLength={200} rows={3} value={draft.text} placeholder="Hello|PCC" onChange={event => onChange({ ...draft, text: event.target.value })} /></label>
        <div className="studio-two-fields"><label>Text colour<input type="color" value={draft.textColor} onChange={event => onChange({ ...draft, textColor: event.target.value })} /></label><label>Background colour<input type="color" value={draft.background} onChange={event => onChange({ ...draft, background: event.target.value })} /></label></div>
        <label>Font size (0 = auto)<input type="number" min="0" max="64" value={draft.textSize} onChange={event => onChange({ ...draft, textSize: Math.max(0, Math.min(64, Math.round(Number(event.target.value)))) })} /></label>
        <button className="secondary" type="button" onClick={renderText}>Create text artwork</button>
      </fieldset>
      <fieldset disabled={transfer.busy}><legend>Crop & conversion</legend>
        {([['cropX', 'Horizontal offset', -100, 100], ['cropY', 'Vertical offset', -100, 100], ['zoom', 'Zoom', 100, 300]] as const).map(([key, label, min, max]) => <label key={key} className="studio-range">{label}<output>{draft[key]}{key === 'zoom' ? '%' : ''}</output><input aria-label={label} type="range" min={min} max={max} value={draft[key]} onChange={event => onChange({ ...draft, [key]: Number(event.target.value) })} /></label>)}
        <label className="tool-confirmation"><input type="checkbox" checked={draft.dither} onChange={event => onChange({ ...draft, dither: event.target.checked })} />Smooth gradients with dithering</label>
        <label>Frame limit<input type="number" min="1" max="120" value={draft.maxFrames} onChange={event => onChange({ ...draft, maxFrames: Math.max(1, Math.min(120, Math.round(Number(event.target.value)))) })} /></label>
      </fieldset>
      {busy && <p role="status" className="device-note">Preparing local artwork…</p>}
    </section>
  </div>;
}

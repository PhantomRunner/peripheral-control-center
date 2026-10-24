import { useRef, useState } from 'react';
import { KeyboardPreview } from './KeyboardPreview';
import { DEFAULT_LIGHTING } from './lighting';
import { keydConfig, MAPPING_KEYS, type KeyMapping } from './keyMapping';
import { download } from './download';

export function KeyMappingPanel({ mappings, onChange, iso }: { mappings: KeyMapping[]; onChange: (value: KeyMapping[]) => void; iso: boolean }) {
  const [monitoring, setMonitoring] = useState(false);
  const [pressed, setPressed] = useState<string[]>([]);
  const [history, setHistory] = useState<{ code: string; key: string; location: number }[]>([]);
  const [from, setFrom] = useState('CapsLock'), [to, setTo] = useState('Escape');
  const monitor = useRef<HTMLDivElement>(null);
  const add = () => onChange([...mappings.filter(mapping => mapping.from !== from), { from, to }]);
  return <div className="studio-screen-grid">
    <section className="panel" aria-labelledby="key-monitor-title">
      <div className="studio-kicker">INPUT / LOCAL</div><h2 id="key-monitor-title">Know your keys.</h2>
      <KeyboardPreview draft={DEFAULT_LIGHTING} iso={iso} pressed={pressed} />
      <p className="device-note">The browser cannot identify which physical keyboard produced an event. Only keys pressed in the focused test area are shown. Fn may be handled inside the keyboard.</p>
      <button className="secondary" type="button" onClick={() => { setMonitoring(true); setHistory([]); monitor.current?.focus(); }}>Start key monitor</button>
      <div className={`studio-key-monitor ${monitoring ? 'active' : ''}`} ref={monitor} tabIndex={0} role="region" aria-label="Key test area" onBlur={() => { setMonitoring(false); setPressed([]); }}
        onKeyDown={event => {
          if (!monitoring || event.key === 'Tab') return;
          event.preventDefault();
          setPressed(keys => [...new Set([...keys, event.code])]);
          if (!event.repeat) {
            setHistory(items => [{ code: event.code, key: event.key, location: event.location }, ...items].slice(0, 12));
            if (MAPPING_KEYS.includes(event.code)) setFrom(event.code);
          }
        }} onKeyUp={event => { if (monitoring) { if (event.key !== 'Tab') event.preventDefault(); setPressed(keys => keys.filter(code => code !== event.code)); } }}>
        {monitoring ? 'Press keys here · Tab leaves the monitor' : 'Start the monitor, then press a key'}
      </div>
      {history.length > 0 && <div className="studio-key-history" aria-label="Recent test keys">{history.map((event, index) => <div key={index}><code>{event.code || 'Unidentified'}</code><span>{event.key} · location {event.location}</span></div>)}</div>}
      <button className="studio-text-button" type="button" onClick={() => { setMonitoring(false); setPressed([]); setHistory([]); }}>Clear key history</button>
    </section>
    <section className="panel studio-form" aria-labelledby="key-remap-title">
      <div className="studio-kicker">LINUX / KEYD EXPORT</div><h2 id="key-remap-title">Key remapping</h2>
      <p className="device-note">Build a Linux mapping for this wired keyboard. Exporting a configuration changes no keys. Applying it requires a separately installed keyd service; this is an OS mapping, not keyboard firmware.</p>
      <div className="studio-two-fields"><label>Source key<select value={from} onChange={event => setFrom(event.target.value)}>{MAPPING_KEYS.map(code => <option key={code}>{code}</option>)}</select></label><label>Target key<select value={to} onChange={event => setTo(event.target.value)}>{MAPPING_KEYS.map(code => <option key={code}>{code}</option>)}</select></label></div>
      <button className="secondary" type="button" disabled={from === to} onClick={add}>Add mapping</button>
      {mappings.length ? <ul className="studio-mappings">{mappings.map(mapping => <li key={mapping.from}><span><code>{mapping.from}</code> → <code>{mapping.to}</code></span><button type="button" className="studio-text-button" aria-label={`Remove mapping ${mapping.from}`} onClick={() => onChange(mappings.filter(item => item.from !== mapping.from))}>Remove</button></li>)}</ul> : <p className="device-note">No local mappings yet. Press a key in the monitor to select its source.</p>}
      <pre className="studio-config" aria-label="Generated keyd configuration">{keydConfig(mappings)}</pre>
      <button type="button" className="secondary" disabled={!mappings.length} onClick={() => download('pcc-ajazz-ak820-pro.conf', keydConfig(mappings), 'text/plain')}>Export keyd configuration</button>
      <p className="device-note">Scoped to wired 0c45:8009. The wireless receiver and other keyboards are excluded. Review with <code>keyd check pcc-ajazz-ak820-pro.conf</code> before installation.</p>
      <a className="detail-link" href="https://github.com/rvaiya/keyd/blob/master/docs/keyd.scdoc" target="_blank" rel="noreferrer">keyd configuration guide ↗</a>
    </section>
  </div>;
}

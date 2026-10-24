import { useId, useRef, useState } from 'react';
import { DeviceDetails } from '../components/DeviceDetails';
import { DeviceStatus } from '../components/DeviceCard';
import { ProfilePanel } from '../components/ProfilePanel';
import type { Device } from '../types';
import { DEFAULT_LIGHTING } from './lighting';
import { LightingPanel } from './LightingPanel';
import { ScreenPanel } from './ScreenPanel';
import { DEFAULT_SCREEN, type ScreenSource } from './screenMedia';
import { KeyMappingPanel } from './KeyMappingPanel';
import type { KeyMapping } from './keyMapping';
import { StudioSettingsPanel } from './StudioSettingsPanel';
import { DEFAULT_PROFILE, type StudioProfile } from './studioProfile';
import './studio.css';

export function KeyboardWorkspace({ device, stale, onUpdated }: { device: Device; stale: boolean; onUpdated: () => Promise<void> }) {
  const [tab, setTab] = useState('lighting');
  const [lighting, setLighting] = useState(DEFAULT_LIGHTING);
  const [iso, setIso] = useState(false);
  const [screen, setScreen] = useState(DEFAULT_SCREEN);
  const [source, setSource] = useState<ScreenSource | null>(null);
  const [mappings, setMappings] = useState<KeyMapping[]>([]);
  const [standbyMinutes, setStandby] = useState(DEFAULT_PROFILE.standbyMinutes);
  const [clockIntervalMinutes, setClockInterval] = useState(DEFAULT_PROFILE.clockIntervalMinutes);
  const profile: StudioProfile = { ...DEFAULT_PROFILE, lighting, screen, mappings, iso, standbyMinutes, clockIntervalMinutes };
  const loadProfile = (next: StudioProfile) => {
    setLighting(next.lighting); setScreen(next.screen); setMappings(next.mappings); setIso(next.iso);
    setStandby(next.standbyMinutes); setClockInterval(next.clockIntervalMinutes);
  };
  const tabId = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const tabs = [['lighting', 'Lighting'], ['screen', 'Screen'], ['keys', 'Key remapping'], ['settings', 'Settings'], ['device', 'Device & profiles']] as const;
  return <div className="keyboard-studio">
    <div className="studio-status-bar"><div><span className="studio-kicker">KEYBOARD STUDIO</span><p>Your keyboard. Your workspace.</p></div><DeviceStatus device={device} stale={stale} /></div>
    <div className="studio-tabs" role="tablist" aria-label="Keyboard studio">{tabs.map(([id, label], index) => <button key={id} ref={element => { buttons.current[index] = element; }} id={`${tabId}-${id}`} type="button" role="tab" aria-selected={tab === id} aria-controls={`${tabId}-panel`} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} onKeyDown={event => {
      let next = index;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault(); setTab(tabs[next][0]); buttons.current[next]?.focus();
    }}>{label}</button>)}</div>
    <div role="tabpanel" id={`${tabId}-panel`} aria-labelledby={`${tabId}-${tab}`}>
      {tab === 'lighting' && <LightingPanel device={device} stale={stale} draft={lighting} onChange={setLighting} iso={iso} onIso={setIso} onUpdated={onUpdated} />}
      {tab === 'screen' && <ScreenPanel draft={screen} onChange={setScreen} source={source} onSource={setSource} />}
      {tab === 'keys' && <KeyMappingPanel mappings={mappings} onChange={setMappings} iso={iso} />}
      {tab === 'settings' && <StudioSettingsPanel profile={profile} onChange={loadProfile} device={device} stale={stale} onUpdated={onUpdated} />}
      {tab === 'device' && <><DeviceDetails device={device} stale={stale} onTelemetryRead={onUpdated} /><ProfilePanel device={device} stale={stale} onUpdated={onUpdated} /></>}
    </div>
  </div>;
}

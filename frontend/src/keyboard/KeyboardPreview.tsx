import { useEffect, useState } from 'react';
import { keyboardKeys } from './layout';
import { keyColor, type LightingDraft } from './lighting';

export function KeyboardPreview({ draft, iso = false, pressed = [] }: { draft: LightingDraft; iso?: boolean; pressed?: string[] }) {
  const [playing, setPlaying] = useState(() => !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  const [time, setTime] = useState(0);
  const animated = !['off', 'static', 'colourful'].includes(draft.effect) || draft.rainbow;
  useEffect(() => {
    if (!playing || !animated) return;
    let handle = 0, last = 0;
    const frame = (now: number) => {
      if (document.visibilityState === 'hidden') { handle = 0; return; }
      if (now - last >= 50) { setTime(now / 1000); last = now; }
      handle = requestAnimationFrame(frame);
    };
    const resume = () => { if (!handle && document.visibilityState !== 'hidden') handle = requestAnimationFrame(frame); };
    resume(); document.addEventListener('visibilitychange', resume);
    return () => { cancelAnimationFrame(handle); document.removeEventListener('visibilitychange', resume); };
  }, [playing, animated]);
  return <div className="keyboard-preview">
    <div className="studio-caption"><span>LOCAL PREVIEW</span><button type="button" className="studio-text-button" onClick={() => setPlaying(!playing)}>{playing ? 'Pause preview' : 'Play preview'}</button></div>
    <svg viewBox="-0.35 -0.35 17.2 6.7" role="img" aria-label={`AK820 Pro ${iso ? 'ISO' : 'ANSI'} keyboard preview`}>
      <rect x="-.3" y="-.3" width="17.1" height="6.6" rx=".28" fill="#0e1420" stroke="#394253" strokeWidth=".04" />
      {keyboardKeys(iso).map((key, index) => <g key={key.code}>
        <rect x={key.x + .04} y={key.y + .05} width={key.w - .08} height={key.h - .1} rx=".09" fill={keyColor(draft, (key.x + key.w / 2) / 16.5, (key.y + key.h / 2) / 6, index / 83, time)} />
        <rect x={key.x + .1} y={key.y + .11} width={key.w - .2} height={key.h - .22} rx=".065" fill={pressed.includes(key.code) ? '#665dd5' : '#202838'} />
        <text x={key.x + key.w / 2} y={key.y + key.h / 2 + .055} textAnchor="middle" fill="#d3d9e8" fontSize=".23" fontFamily="system-ui, sans-serif">{key.label}</text>
      </g>)}
      <circle cx="16" cy=".5" r=".39" fill="#293344" stroke="#7c88a0" strokeWidth=".06" />
      <path d="M16 .18v.15" stroke="#c2c9df" strokeWidth=".05" />
      <rect x="15.53" y="4.08" width=".94" height=".84" rx=".09" fill="#060b14" stroke="#58677d" strokeWidth=".04" />
      <text x="16" y="4.57" textAnchor="middle" fill="#9f98ff" fontSize=".2">TFT</text>
    </svg>
    <p className="device-note">Simulated effect and key legends. Current lighting is not read from the keyboard.</p>
  </div>;
}

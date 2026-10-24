/* Preview math adapted from kabelklaus/ajazz-ak820-pro (MIT, Copyright (c) 2026 kabelklaus).
 * Reference 4b69f3cb57506f518e5b2f9f5f56e07e8b9411d6; full notice in LICENSE.ajazz-ak820-pro.
 * This module simulates light only. It contains no HID transport or packet encoding.
 */
export const EFFECTS = [
  ['off', 'Off'], ['static', 'Static'], ['key_on', 'Key on'], ['key_off', 'Key off'],
  ['glitter', 'Glitter'], ['falling', 'Falling'], ['colourful', 'Colourful'], ['breathe', 'Breathe'],
  ['spectrum', 'Spectrum'], ['outward', 'Outward'], ['scroll', 'Scroll'], ['roll', 'Roll'],
  ['rotate', 'Rotate'], ['explode', 'Explode'], ['launch', 'Launch'], ['ripple', 'Ripple'],
  ['flow', 'Flow'], ['pulse', 'Pulse'], ['tilt', 'Tilt'], ['shuttle', 'Shuttle'],
] as const;
export type Effect = typeof EFFECTS[number][0];
export type Direction = 'left' | 'down' | 'up' | 'right';
export type LightingDraft = { effect: Effect; color: string; brightness: number; speed: number; direction: Direction; rainbow: boolean };
export const DEFAULT_LIGHTING: LightingDraft = { effect: 'static', color: '#4080ff', brightness: 60, speed: 0, direction: 'left', rainbow: false };
export const directional = (effect: Effect) => ['scroll', 'roll', 'flow', 'tilt'].includes(effect);
export const verifiedStatic = (draft: LightingDraft) => draft.effect === 'static' && !draft.rainbow && draft.speed === 0 && draft.direction === 'left';

function hsv(hue: number): number[] {
  const h = ((hue % 1) + 1) % 1 * 6, i = Math.floor(h), f = h - i;
  return ([[1, f, 0], [1 - f, 1, 0], [0, 1, f], [0, 1 - f, 1], [f, 0, 1], [1, 0, 1 - f]][i % 6]).map(v => Math.round(v * 255));
}
const wave = (x: number) => { x = ((x % 1) + 1) % 1; return x < .5 ? x * 2 : 2 - x * 2; };
const band = (pos: number, head: number, width: number) => Math.max(0, 1 - Math.abs(((pos - head + 1.5) % 1) - .5) * 2 / width);
const hash = (a: number, b: number) => { const n = Math.sin(a * 127.1 + b * 311.7) * 43758.5453; return n - Math.floor(n); };

export function keyColor(draft: LightingDraft, x: number, y: number, seed: number, seconds: number): string {
  const t = seconds * (.35 + draft.speed * .38), dx = x - .5, dy = y - .5;
  const along = draft.direction === 'left' ? x : draft.direction === 'right' ? 1 - x : draft.direction === 'up' ? y : 1 - y;
  let light = 1, hue: number | null = null;
  switch (draft.effect) {
    case 'off': light = 0; break;
    case 'key_on': light = hash(seed, Math.floor(t * 2)) > .85 ? 1 : .06; break;
    case 'key_off': light = hash(seed, Math.floor(t * 2)) > .85 ? .06 : 1; break;
    case 'glitter': light = Math.pow(Math.max(0, wave(t * .9 + seed * 7) * 2 - 1), 3); break;
    case 'falling': light = Math.max(0, 1 - Math.abs(((t * .5 + seed) % 1) - y) * 6); break;
    case 'colourful': hue = seed; break;
    case 'breathe': light = .08 + .92 * (Math.sin(t * 2) * .5 + .5); break;
    case 'spectrum': hue = t * .15; break;
    case 'outward': light = band(Math.hypot(dx, dy * .6) * 2, t * .4, .5); break;
    case 'scroll': light = band(along, t * .4, .45); break;
    case 'roll': hue = along - t * .25; break;
    case 'rotate': hue = Math.atan2(dy, dx) / (Math.PI * 2) + t * .2; break;
    case 'explode': {
      const cycle = Math.floor(t * .7), phase = (t * .7) % 1;
      light = band(Math.hypot(x - hash(cycle, 1), (y - hash(cycle, 2)) * .6) * 1.6, phase, .45) * (1 - phase); break;
    }
    case 'launch': light = Math.max(0, 1 - Math.abs(1 - y - (t * .5) % 1) * 5); break;
    case 'ripple': {
      const cycle = Math.floor(t * .5), phase = (t * .5) % 1;
      light = Math.max(0, Math.sin((Math.hypot(x - hash(cycle, 3), (y - hash(cycle, 4)) * .6) * 1.6 - phase) * Math.PI * 4)) * (1 - phase); break;
    }
    case 'flow': hue = along * .8 - t * .2; break;
    case 'pulse': light = .1 + .9 * Math.max(0, Math.sin(t * 2.4 - x * 4)); break;
    case 'tilt': light = band((x + y) / 2, t * .4, .5); break;
    case 'shuttle': light = band(along, wave(t * .35), .4); break;
  }
  if (draft.rainbow && hue === null) hue = x * .6 + t * .15;
  const rgb = hue === null ? [1, 3, 5].map(offset => parseInt(draft.color.slice(offset, offset + 2), 16)) : hsv(hue);
  const gain = Math.max(0, Math.min(1, light)) * draft.brightness / 100;
  return `rgb(${rgb.map(v => Math.round(v * gain)).join(',')})`;
}

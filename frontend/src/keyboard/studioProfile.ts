import { DEFAULT_LIGHTING, EFFECTS, type LightingDraft } from './lighting';
import { DEFAULT_SCREEN, type ScreenDraft } from './screenMedia';
import { keydConfig, type KeyMapping } from './keyMapping';

export type StudioProfile = {
  tool: 'pcc-keyboard-studio'; version: 1; device_id: 'ajazz_ak820_pro';
  lighting: LightingDraft; screen: ScreenDraft; mappings: KeyMapping[];
  iso: boolean; standbyMinutes: number; clockIntervalMinutes: number;
};
export const DEFAULT_PROFILE: StudioProfile = { tool: 'pcc-keyboard-studio', version: 1, device_id: 'ajazz_ak820_pro',
  lighting: DEFAULT_LIGHTING, screen: DEFAULT_SCREEN, mappings: [], iso: false, standbyMinutes: 5, clockIntervalMinutes: 30 };
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const integer = (value: unknown, min: number, max: number): value is number => typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;
const color = (value: unknown): value is string => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value);

function validate(value: unknown): StudioProfile {
  if (!record(value) || value.tool !== DEFAULT_PROFILE.tool || value.version !== 1 || value.device_id !== DEFAULT_PROFILE.device_id
    || typeof value.iso !== 'boolean' || !integer(value.clockIntervalMinutes, 1, 1440)
    || ![0,1,5,30].includes(value.standbyMinutes as number) || !record(value.lighting) || !record(value.screen)
    || !Array.isArray(value.mappings) || value.mappings.length > 82) throw new Error('Invalid keyboard Studio profile.');
  const light = value.lighting, screen = value.screen;
  if (!EFFECTS.some(([id]) => id === light.effect) || !color(light.color) || !integer(light.brightness, 0, 100) || light.brightness % 20 !== 0
    || !integer(light.speed, 0, 5) || !['left','down','up','right'].includes(light.direction as string) || typeof light.rainbow !== 'boolean'
    || typeof screen.text !== 'string' || screen.text.length > 200 || !color(screen.textColor) || !color(screen.background)
    || !integer(screen.textSize, 0, 64) || !integer(screen.cropX, -100, 100) || !integer(screen.cropY, -100, 100)
    || !integer(screen.zoom, 100, 300) || typeof screen.dither !== 'boolean' || !integer(screen.maxFrames, 1, 120)
    || value.mappings.some(item => !record(item) || typeof item.from !== 'string' || typeof item.to !== 'string')) throw new Error('Profile values are outside supported draft bounds.');
  const mappings = value.mappings.map(item => ({ from: item.from as string, to: item.to as string }));
  keydConfig(mappings); // Reject directive injection, unknown keys and duplicate sources.
  // Rebuild allowlisted fields; tokens, commands, flags and prototype fields are never imported.
  return { ...DEFAULT_PROFILE,
    lighting: { effect: light.effect as LightingDraft['effect'], color: light.color.toLowerCase(), brightness: light.brightness, speed: light.speed, direction: light.direction as LightingDraft['direction'], rainbow: light.rainbow },
    screen: { text: screen.text, textColor: screen.textColor.toLowerCase(), background: screen.background.toLowerCase(), textSize: screen.textSize, cropX: screen.cropX, cropY: screen.cropY, zoom: screen.zoom, dither: screen.dither, maxFrames: screen.maxFrames },
    mappings, iso: value.iso, standbyMinutes: value.standbyMinutes as number, clockIntervalMinutes: value.clockIntervalMinutes,
  };
}

function legacyNumber(value: unknown, fallback: number): number {
  if (value === undefined) return fallback;
  if (typeof value === 'number' && Number.isInteger(value)) return value;
  if (typeof value === 'string' && /^-?\d{1,4}$/.test(value)) return Number(value);
  throw new Error('Invalid numeric setting in the imported profile.');
}

export function parseStudioProfile(text: string): StudioProfile {
  if (text.length > 65_536) throw new Error('Profile exceeds 64 KiB.');
  let value: unknown;
  try { value = JSON.parse(text); } catch { throw new Error('Choose a valid JSON profile.'); }
  if (record(value) && value.tool === 'ak820-debug' && value.version === 1 && record(value.settings)) {
    const s = value.settings;
    const effect = legacyNumber(s.rgbMode, 1), direction = legacyNumber(s.rgbDir, 0), standby = legacyNumber(s.sleepTime, 2);
    return validate({ ...DEFAULT_PROFILE,
      lighting: { effect: EFFECTS[effect]?.[0], color: s.rgbColor ?? DEFAULT_LIGHTING.color,
        brightness: legacyNumber(s.rgbBright, 3) * 20, speed: legacyNumber(s.rgbSpeed, 0), direction: ['left','down','up','right'][direction], rainbow: s.rgbRainbow ?? false },
      screen: { text: s.txtLines ?? DEFAULT_SCREEN.text, textColor: s.txtColor ?? DEFAULT_SCREEN.textColor, background: s.txtBg ?? DEFAULT_SCREEN.background,
        textSize: legacyNumber(s.txtSize, 0), cropX: legacyNumber(s.cropX, 0), cropY: legacyNumber(s.cropY, 0), zoom: legacyNumber(s.zoom, 100),
        dither: s.dither ?? false, maxFrames: legacyNumber(s.maxFrames, 120) },
      standbyMinutes: [0,1,5,30][standby], clockIntervalMinutes: legacyNumber(s.autoSyncMin, 30),
    });
  }
  return validate(value);
}

export function exportStudioProfile(value: StudioProfile): string {
  return JSON.stringify(validate(value), null, 2);
}

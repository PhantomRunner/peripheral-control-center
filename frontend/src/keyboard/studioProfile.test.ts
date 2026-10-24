import { expect, it } from 'vitest';
import { DEFAULT_PROFILE, exportStudioProfile, parseStudioProfile } from './studioProfile';

it('round-trips bounded drafts without device consent, commands or image data', () => {
  const value = { ...DEFAULT_PROFILE, mappings: [{ from: 'CapsLock', to: 'Escape' }],
    lighting: { ...DEFAULT_PROFILE.lighting, effect: 'flow' as const, direction: 'right' as const, speed: 4, rainbow: true } };
  expect(parseStudioProfile(exportStudioProfile(value))).toEqual(value);
  const serialized = exportStudioProfile({ ...value, token: 'private', vendor_tools_closed: true, autoSync: true } as typeof value);
  expect(serialized).not.toContain('private'); expect(serialized).not.toContain('vendor_tools_closed'); expect(serialized).not.toContain('autoSync');
});

it('imports original Studio v1 desired settings but ignores unsafe persistence/auto-sync switches', () => {
  const result = parseStudioProfile(JSON.stringify({ tool: 'ak820-debug', version: 1, settings: {
    rgbMode: '7', rgbColor: '#FF0000', rgbBright: '4', rgbSpeed: '3', rgbDir: '2', rgbRainbow: true,
    sleepTime: '3', cropX: '-20', zoom: '150', txtLines: 'Hello|World', autoSyncMin: '15', saveFinish: true, saveByte8: '01', autoSync: true,
  } }));
  expect(result.lighting).toEqual({ effect: 'breathe', color: '#ff0000', brightness: 80, speed: 3, direction: 'up', rainbow: true });
  expect(result.standbyMinutes).toBe(30); expect(result.screen.cropX).toBe(-20); expect(result.screen.zoom).toBe(150);
  expect(result.clockIntervalMinutes).toBe(15);
  expect(JSON.stringify(result)).not.toContain('saveFinish'); expect(JSON.stringify(result)).not.toContain('autoSync');
});

it.each([
  { ...DEFAULT_PROFILE, version: 2 }, { ...DEFAULT_PROFILE, device_id: 'other' },
  { ...DEFAULT_PROFILE, standbyMinutes: 2 }, { ...DEFAULT_PROFILE, screen: { ...DEFAULT_PROFILE.screen, zoom: 0 } },
  { ...DEFAULT_PROFILE, lighting: { ...DEFAULT_PROFILE.lighting, brightness: 61 } },
  { tool: 'ak820-debug', version: 1, settings: { rgbBright: false } },
  { ...DEFAULT_PROFILE, mappings: [{ from: 'KeyA', to: 'esc\n[ids]\n*' }] },
])('rejects unsupported or coercible profile values (%#)', value => {
  expect(() => parseStudioProfile(JSON.stringify(value))).toThrow();
});

it('rejects broken or oversized input before it can replace the local draft', () => {
  expect(() => parseStudioProfile('{')).toThrow('valid JSON');
  expect(() => parseStudioProfile(' '.repeat(65_537))).toThrow('64 KiB');
});

import { describe, expect, it } from 'vitest';
import type { ParsedFrame } from 'gifuct-js';
import { compositeGif, cropRect, decodeGif, decodeRgb565, DEFAULT_SCREEN, encodeRgb565, FRAME_BYTES, screenPayload } from './screenMedia';

describe('local TFT media conversion', () => {
  it('encodes RGB565 in little-endian order and previews quantized pixels', () => {
    const rgba = new Uint8ClampedArray(128 * 128 * 4);
    rgba.set([255,0,0,255, 0,255,0,255, 0,0,255,255, 255,255,255,255]);
    const packed = encodeRgb565(rgba);
    expect([...packed.slice(0, 8)]).toEqual([0,248, 224,7, 31,0, 255,255]);
    expect(packed.length).toBe(FRAME_BYTES);
    expect([...decodeRgb565(packed).slice(0, 16)]).toEqual([...rgba.slice(0, 16)]);
    rgba.set([123,123,123,255]);
    expect([...decodeRgb565(encodeRgb565(rgba)).slice(0, 4)]).toEqual([123,121,123,255]);
  });

  it('dithers gradients without modifying source pixels or frame bounds', () => {
    const rgba = new Uint8ClampedArray(128 * 128 * 4).fill(130), before = rgba.slice();
    const plain = encodeRgb565(rgba), dithered = encodeRgb565(rgba, true);
    expect(dithered).not.toEqual(plain);
    expect(dithered.length).toBe(plain.length);
    expect(rgba).toEqual(before);
  });

  it('crops to a bounded square and honors offset and zoom', () => {
    expect(cropRect(300, 100, DEFAULT_SCREEN)).toEqual({ x: 100, y: 0, size: 100 });
    expect(cropRect(300, 100, { cropX: -100, cropY: 100, zoom: 100 })).toEqual({ x: 0, y: 0, size: 100 });
    expect(cropRect(100, 100, { cropX: 100, cropY: -100, zoom: 200 })).toEqual({ x: 50, y: 0, size: 50 });
  });

  it('exports a bounded frame header and pads to 4096 bytes with FF', () => {
    const frame = { rgb565: new Uint8Array(FRAME_BYTES).fill(42), rgba: new Uint8ClampedArray(), delayMs: 1000 };
    const one = screenPayload([frame]);
    expect(one.length).toBe(9 * 4096);
    expect([...one.slice(0, 4)]).toEqual([1,0,255,255]);
    expect(one[256]).toBe(42); expect(one[one.length - 1]).toBe(255);
    const two = screenPayload([frame, { ...frame, delayMs: 1 }]);
    expect([...two.slice(0, 4)]).toEqual([2,255,1,255]);
    expect(() => screenPayload([])).toThrow();
    expect(() => screenPayload(Array(121).fill(frame))).toThrow();
  });

  it('decodes a real two-frame GIF with separate red/blue frames and delays', async () => {
    const bytes = new Uint8Array([
      ...[...'GIF89a'].map(c => c.charCodeAt(0)), 1,0,1,0,128,0,0, 255,0,0, 0,0,255,
      33,249,4,8,10,0,0,0, 44,0,0,0,0,1,0,1,0,0, 2,2,68,1,0,
      33,249,4,8,20,0,0,0, 44,0,0,0,0,1,0,1,0,0, 2,2,76,1,0, 59,
    ]);
    const frames = await decodeGif(bytes.buffer);
    expect(frames).toHaveLength(2);
    expect([...frames[0].rgba]).toEqual([255,0,0,255]);
    expect([...frames[1].rgba]).toEqual([0,0,255,255]);
    expect(frames.map(frame => frame.delayMs)).toEqual([100,200]);
  });

  it('honors GIF background/previous disposal and rejects oversize patches', () => {
    const patch = (left: number, rgba: number[], disposalType = 1) => ({ dims: { left, top: 0, width: 1, height: 1 }, patch: new Uint8ClampedArray(rgba), disposalType, delay: 100 } as ParsedFrame);
    const red = patch(0, [255,0,0,255]), green = patch(1, [0,255,0,255], 3), transparent = patch(1, [0,0,0,0]);
    const result = compositeGif(2, 1, [red, green, transparent]);
    expect([...result[1].rgba.slice(4)]).toEqual([0,255,0,255]);
    expect([...result[2].rgba.slice(4)]).toEqual([0,0,0,0]);
    const cleared = compositeGif(2, 1, [{ ...red, disposalType: 2 }, transparent], [0,0,255,255]);
    expect([...cleared[1].rgba.slice(0,4)]).toEqual([0,0,255,255]);
    expect(() => compositeGif(1, 1, [green])).toThrow('bounds');
    expect(() => compositeGif(4096, 4096, [red, red])).toThrow('limit');
  });
});

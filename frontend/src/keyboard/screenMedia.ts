/* RGB565 conversion/crop based on kabelklaus/ajazz-ak820-pro, MIT (c) 2026 kabelklaus.
 * Full notice: LICENSE.ajazz-ak820-pro. This file processes local media, never HID.
 */
import type { ParsedFrame } from 'gifuct-js';

export const SCREEN_SIZE = 128;
export const FRAME_BYTES = SCREEN_SIZE * SCREEN_SIZE * 2;
export const MAX_FRAMES = 120;
const MAX_PIXELS = 16_777_216;
export type RawFrame = { rgba: Uint8ClampedArray; width: number; height: number; delayMs: number };
export type ScreenSource = { name: string; frames: RawFrame[] };
export type ScreenDraft = { text: string; textColor: string; background: string; textSize: number; cropX: number; cropY: number; zoom: number; dither: boolean; maxFrames: number };
export type ScreenFrame = { rgb565: Uint8Array; rgba: Uint8ClampedArray; delayMs: number };
export const DEFAULT_SCREEN: ScreenDraft = { text: 'Hello|PCC', textColor: '#ffffff', background: '#000000', textSize: 0, cropX: 0, cropY: 0, zoom: 100, dither: false, maxFrames: MAX_FRAMES };

export function encodeRgb565(rgba: Uint8ClampedArray, dither = false): Uint8Array {
  if (rgba.length !== SCREEN_SIZE * SCREEN_SIZE * 4) throw new Error('A screen frame must be 128 × 128 RGBA pixels.');
  const pixels = new Float32Array(rgba);
  const output = new Uint8Array(FRAME_BYTES);
  const spread = [[1, 0, 7 / 16], [-1, 1, 3 / 16], [0, 1, 5 / 16], [1, 1, 1 / 16]];
  for (let y = 0; y < SCREEN_SIZE; y++) for (let x = 0; x < SCREEN_SIZE; x++) {
    const i = (y * SCREEN_SIZE + x) * 4;
    const rgb = [0, 1, 2].map(channel => {
      const value = Math.max(0, Math.min(255, pixels[i + channel]));
      const bits = channel === 1 ? 6 : 5;
      const quantized = Math.round(value * ((1 << bits) - 1) / 255);
      if (dither) for (const [dx, dy, factor] of spread) {
        const nx = x + dx, ny = y + dy;
        if (nx >= 0 && nx < SCREEN_SIZE && ny < SCREEN_SIZE) pixels[(ny * SCREEN_SIZE + nx) * 4 + channel] += (value - quantized * 255 / ((1 << bits) - 1)) * factor;
      }
      return dither ? quantized : channel === 1 ? value >> 2 : value >> 3;
    });
    const word = (rgb[0] << 11) | (rgb[1] << 5) | rgb[2];
    output[(i / 4) * 2] = word & 255;
    output[(i / 4) * 2 + 1] = word >> 8;
  }
  return output;
}

export function decodeRgb565(bytes: Uint8Array): Uint8ClampedArray {
  if (bytes.length !== FRAME_BYTES) throw new Error('Invalid RGB565 frame length.');
  const rgba = new Uint8ClampedArray(SCREEN_SIZE * SCREEN_SIZE * 4);
  for (let i = 0; i < bytes.length; i += 2) {
    const word = bytes[i] | (bytes[i + 1] << 8), r = word >> 11, g = (word >> 5) & 63, b = word & 31;
    rgba.set([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), 255], i * 2);
  }
  return rgba;
}

export function cropRect(width: number, height: number, draft: Pick<ScreenDraft, 'cropX' | 'cropY' | 'zoom'>) {
  const size = Math.min(width, height) / (draft.zoom / 100);
  return { x: Math.max(0, Math.min(width - size, (width - size) / 2 * (1 + draft.cropX / 100))),
    y: Math.max(0, Math.min(height - size, (height - size) / 2 * (1 + draft.cropY / 100))), size };
}

function canvas(width: number, height: number) {
  const surface = document.createElement('canvas'); surface.width = width; surface.height = height;
  const context = surface.getContext('2d', { willReadFrequently: true });
  if (!context) throw new Error('Canvas rendering is unavailable in this browser.');
  return { surface, context };
}

export function compileScreen(source: ScreenSource, draft: ScreenDraft): ScreenFrame[] {
  return source.frames.slice(0, draft.maxFrames).map(frame => {
    const original = canvas(frame.width, frame.height);
    original.context.putImageData(new ImageData(new Uint8ClampedArray(frame.rgba), frame.width, frame.height), 0, 0);
    const work = canvas(SCREEN_SIZE, SCREEN_SIZE), crop = cropRect(frame.width, frame.height, draft);
    work.context.fillStyle = draft.background; work.context.fillRect(0, 0, SCREEN_SIZE, SCREEN_SIZE);
    work.context.drawImage(original.surface, crop.x, crop.y, crop.size, crop.size, 0, 0, SCREEN_SIZE, SCREEN_SIZE);
    const rgb565 = encodeRgb565(work.context.getImageData(0, 0, SCREEN_SIZE, SCREEN_SIZE).data, draft.dither);
    return { rgb565, rgba: decodeRgb565(rgb565), delayMs: frame.delayMs };
  });
}

export function textSource(draft: ScreenDraft): ScreenSource {
  const lines = draft.text.split(/[|\n]/).map(line => line.trim()).filter(Boolean).slice(0, 5);
  if (!lines.length) throw new Error('Enter some text first.');
  const { context } = canvas(SCREEN_SIZE, SCREEN_SIZE);
  context.fillStyle = draft.background; context.fillRect(0, 0, SCREEN_SIZE, SCREEN_SIZE);
  let size = draft.textSize || 64;
  if (!draft.textSize) while (size > 8) {
    context.font = `600 ${size}px system-ui, sans-serif`;
    if (lines.every(line => context.measureText(line).width <= 118) && lines.length * size * 1.2 <= 118) break;
    size--;
  }
  context.font = `600 ${size}px system-ui, sans-serif`;
  context.fillStyle = draft.textColor; context.textAlign = 'center'; context.textBaseline = 'middle';
  lines.forEach((line, index) => context.fillText(line, 64, 64 + (index - (lines.length - 1) / 2) * size * 1.2, 118));
  return { name: 'Text artwork', frames: [{ rgba: context.getImageData(0, 0, SCREEN_SIZE, SCREEN_SIZE).data, width: SCREEN_SIZE, height: SCREEN_SIZE, delayMs: 0 }] };
}

export function compositeGif(width: number, height: number, frames: ParsedFrame[], background = [0, 0, 0, 0]): RawFrame[] {
  if (!width || !height || width * height * frames.length > MAX_PIXELS || !frames.length || frames.length > MAX_FRAMES) throw new Error('Animation exceeds the local processing limit (120 frames / 16 million pixels).');
  let screen = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < screen.length; i += 4) screen.set(background, i);
  return frames.map(frame => {
    const { left, top, width: w, height: h } = frame.dims;
    if (left < 0 || top < 0 || left + w > width || top + h > height || frame.patch.length !== w * h * 4) throw new Error('Invalid GIF frame bounds.');
    const previous = frame.disposalType === 3 ? screen.slice() : null;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const offset = (y * w + x) * 4;
      if (frame.patch[offset + 3]) screen.set(frame.patch.subarray(offset, offset + 4), ((y + top) * width + x + left) * 4);
    }
    const result = { rgba: screen.slice(), width, height, delayMs: Math.max(20, frame.delay || 100) };
    if (frame.disposalType === 2) for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) screen.set(background, ((y + top) * width + x + left) * 4);
    else if (previous) screen = previous;
    return result;
  });
}

export async function decodeGif(buffer: ArrayBuffer): Promise<RawFrame[]> {
  const { parseGIF, decompressFrames } = await import('gifuct-js');
  const gif = parseGIF(buffer);
  if (gif.header.signature !== 'GIF' || !['87a', '89a'].includes(gif.header.version)) throw new Error('Invalid GIF file.');
  const images = gif.frames.filter(frame => 'image' in frame);
  const { width, height } = gif.lsd;
  if (!width || !height || width * height * images.length > MAX_PIXELS || !images.length || images.length > MAX_FRAMES) throw new Error('GIF exceeds 120 frames / 16 million decoded pixels.');
  for (const frame of images) {
    const d = frame.image.descriptor;
    if (!d.width || !d.height || d.left + d.width > width || d.top + d.height > height || frame.image.data.minCodeSize < 2 || frame.image.data.minCodeSize > 8) throw new Error('Invalid GIF dimensions or encoding.');
  }
  // GIF background is transparent when the first frame declares transparency.
  const transparent = images[0].gce?.extras.transparentColorGiven;
  const rgb = gif.gct?.[gif.lsd.backgroundColorIndex] ?? [0, 0, 0];
  return compositeGif(width, height, decompressFrames(gif, true), transparent ? [0, 0, 0, 0] : [...rgb, 255]);
}

export async function loadScreenFile(file: File): Promise<ScreenSource> {
  if (file.size > 10 * 1024 * 1024) throw new Error('Choose an image smaller than 10 MiB.');
  if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(file.type)) throw new Error('Choose PNG, JPEG, WebP or GIF.');
  if (file.type === 'image/gif') return { name: file.name, frames: await decodeGif(await file.arrayBuffer()) };
  const bitmap = await createImageBitmap(file);
  try {
    if (bitmap.width * bitmap.height > MAX_PIXELS) throw new Error('Image exceeds 16 million pixels.');
    const work = canvas(bitmap.width, bitmap.height);
    work.context.drawImage(bitmap, 0, 0);
    return { name: file.name, frames: [{ rgba: work.context.getImageData(0, 0, bitmap.width, bitmap.height).data, width: bitmap.width, height: bitmap.height, delayMs: 0 }] };
  } finally { bitmap.close(); }
}

export function screenPayload(frames: ScreenFrame[]): Uint8Array {
  if (!frames.length || frames.length > MAX_FRAMES || frames.some(frame => frame.rgb565.length !== FRAME_BYTES)) throw new Error('Invalid screen frame data.');
  const payload = new Uint8Array(Math.ceil((256 + frames.length * FRAME_BYTES) / 4096) * 4096).fill(255);
  payload[0] = frames.length;
  frames.forEach((frame, index) => {
    payload[index + 1] = frames.length === 1 ? 0 : Math.max(1, Math.min(255, Math.round(frame.delayMs / 2)));
    payload.set(frame.rgb565, 256 + index * FRAME_BYTES);
  });
  return payload;
}

import { LocalApiClient } from '../localApi';
import { studioError } from './studioApi';
import type { ScreenFrame } from './screenMedia';

export type ScreenJob = { id: string; status: 'running' | 'transfer_completed' | 'failed'; frame_count: number; total_blocks: number; actual_settings: null; persistence_verified: false; detail: string | null };
const path = '/api/devices/ajazz_ak820_pro/studio/screen/jobs';
function parse(value: unknown): ScreenJob {
  if (typeof value !== 'object' || value === null) throw new Error('Unexpected screen transfer status.');
  const data = value as Record<string, unknown>;
  if (typeof data.id !== 'string' || !/^[a-f0-9]{32}$/.test(data.id) || !['running','transfer_completed','failed'].includes(data.status as string)
    || typeof data.frame_count !== 'number' || !Number.isInteger(data.frame_count) || data.frame_count < 1 || data.frame_count > 120
    || data.total_blocks !== Math.ceil((256 + data.frame_count * 32768) / 4096) || data.actual_settings !== null || data.persistence_verified !== false
    || !(data.detail === null || typeof data.detail === 'string')) throw new Error('Unexpected screen transfer status.');
  // Server failure details are intentionally not rendered; retain a generic local message.
  return { ...data, detail: data.status === 'failed' ? 'Screen transfer was not confirmed. Artwork may have changed; check before retrying.' : null } as ScreenJob;
}
export function encodeFrame(frame: ScreenFrame) {
  if (frame.rgb565.length !== 32768) throw new Error('Invalid screen frame length.');
  let binary = '';
  for (let offset = 0; offset < frame.rgb565.length; offset += 1024) binary += String.fromCharCode(...frame.rgb565.subarray(offset, offset + 1024));
  return { rgb565_base64: btoa(binary), delay_ms: frame.delayMs };
}
export class ScreenClient {
  private api = new LocalApiClient();
  async start(frames: ScreenFrame[], toolsClosed = false, memoryAllowed = false): Promise<ScreenJob> {
    if (!frames.length || frames.length > 120) throw new Error('Choose between 1 and 120 screen frames.');
    let data: unknown;
    try { data = await this.api.request(path, 'POST', { frames: frames.map(encodeFrame), vendor_tools_closed: toolsClosed, allow_device_memory_writes: memoryAllowed }); }
    catch (cause) { throw studioError(cause); }
    const job = parse(data);
    if (job.frame_count !== frames.length) throw new Error('The screen job does not match the artwork. Check before retrying.');
    return job;
  }
  async status(id: string): Promise<ScreenJob> {
    if (!/^[a-f0-9]{32}$/.test(id)) throw new Error('Invalid screen job.');
    const job = parse(await this.api.request(`${path}/${id}`));
    if (job.id !== id) throw new Error('Screen job status did not match.');
    return job;
  }
}

import { LocalApiClient, LocalApiError } from '../localApi';
import type { LightingDraft } from './lighting';

export type StudioIntent = { operation: 'lighting'; settings: LightingDraft } | { operation: 'clock'; local_time: string } | { operation: 'standby'; minutes: number };

export function localClockTime(now = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  const offset = -now.getTimezoneOffset();
  return `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}${offset < 0 ? '-' : '+'}${pad(Math.floor(Math.abs(offset)/60))}:${pad(Math.abs(offset)%60)}`;
}

function record(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value); }
function matchingIntent(actual: unknown, expected: StudioIntent): boolean {
  if (!record(actual) || actual.operation !== expected.operation) return false;
  if (expected.operation === 'clock') return typeof actual.local_time === 'string' && Number.isFinite(Date.parse(actual.local_time)) && Date.parse(actual.local_time) === Date.parse(expected.local_time);
  if (expected.operation === 'standby') return actual.minutes === expected.minutes;
  if (!record(actual.settings)) return false;
  const settings = actual.settings;
  return (Object.keys(expected.settings) as (keyof LightingDraft)[]).every(key => settings[key] === expected.settings[key]);
}

export function studioError(cause: unknown): Error {
  if (cause instanceof LocalApiError) {
    if (cause.status === 409) return new Error('Connect the wired keyboard and confirm tool closure and device-memory writes.');
    if (cause.status === 423) return new Error('The keyboard is busy. Wait for the current operation to finish.');
    if (cause.status === 422 || cause.status === 413) return new Error('These Studio settings exceed the supported limits.');
    if (cause.status === 502 || cause.status === 503) return new Error('The device operation was not confirmed. Settings may have changed; check before retrying.');
  }
  return cause instanceof Error ? cause : new Error('The Studio operation was not confirmed.');
}

export class StudioClient {
  readonly api = new LocalApiClient();
  async apply(intent: StudioIntent, toolsClosed = false, memoryAllowed = false): Promise<void> {
    let value: unknown;
    try { value = await this.api.request('/api/devices/ajazz_ak820_pro/studio/apply', 'POST', { intent, vendor_tools_closed: toolsClosed, allow_device_memory_writes: memoryAllowed }); }
    catch (cause) { throw studioError(cause); }
    if (!record(value) || value.status !== 'acknowledged' || value.device_id !== 'ajazz_ak820_pro'
      || value.actual_settings !== null || value.persistence_verified !== false || !matchingIntent(value.requested, intent)) {
      throw new Error('No matching Studio acknowledgement was received. Settings may have changed.');
    }
  }
}

import { LocalApiClient } from './localApi';

export type MouseSettings = { kind: 'mouse'; dpi: number | null; polling_rate_hz: number | null };
export type KeyboardSettings = { kind: 'keyboard'; rgb: { mode: 'static'; color: string; brightness_percent: number } };
export type SettingsIntent = MouseSettings | KeyboardSettings;
export type ProfileDraft = { name: string; device_id: 'pulsar_susanto_x' | 'ajazz_ak820_pro'; settings: SettingsIntent };
export type SoftwareProfile = ProfileDraft & { id: string; revision: number };

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function integer(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;
}

export function isSettings(value: unknown): value is SettingsIntent {
  if (!record(value)) return false;
  if (value.kind === 'mouse') {
    return (value.dpi === null || integer(value.dpi, 1, 32000))
      && (value.polling_rate_hz === null || (typeof value.polling_rate_hz === 'number' && [125, 250, 500, 1000, 2000, 4000, 8000].includes(value.polling_rate_hz)))
      && (value.dpi !== null || value.polling_rate_hz !== null);
  }
  return value.kind === 'keyboard' && record(value.rgb) && value.rgb.mode === 'static'
    && typeof value.rgb.color === 'string' && /^#[0-9a-f]{6}$/i.test(value.rgb.color)
    && integer(value.rgb.brightness_percent, 0, 100);
}

function isProfile(value: unknown): value is SoftwareProfile {
  if (!record(value) || !isSettings(value.settings)) return false;
  return typeof value.id === 'string' && /^[a-f0-9]{32}$/.test(value.id)
    && integer(value.revision, 1, Number.MAX_SAFE_INTEGER)
    && typeof value.name === 'string' && value.name.trim().length > 0 && value.name.length <= 64
    && (value.device_id === 'pulsar_susanto_x' ? value.settings.kind === 'mouse'
      : value.device_id === 'ajazz_ak820_pro' && value.settings.kind === 'keyboard');
}

function profile(value: unknown): SoftwareProfile {
  if (!isProfile(value)) throw new Error('Unexpected profile response.');
  return value;
}

export class ProfileClient {
  private api = new LocalApiClient();

  async list(signal?: AbortSignal): Promise<SoftwareProfile[]> {
    const value = await this.api.request('/api/profiles', 'GET', undefined, signal);
    if (!record(value) || !Array.isArray(value.profiles) || !value.profiles.every(isProfile)
      || new Set(value.profiles.map((item) => item.id)).size !== value.profiles.length) {
      throw new Error('Unexpected profile response.');
    }
    return value.profiles;
  }

  async save(draft: ProfileDraft, current: SoftwareProfile | null): Promise<SoftwareProfile> {
    const path = current ? `/api/profiles/${current.id}` : '/api/profiles';
    return profile(await this.api.request(path, current ? 'PUT' : 'POST', current ? { ...draft, revision: current.revision } : draft));
  }

  async remove(current: SoftwareProfile): Promise<void> {
    const value = await this.api.request(`/api/profiles/${current.id}`, 'DELETE', { revision: current.revision });
    if (!record(value) || value.deleted !== true) throw new Error('Unexpected profile response.');
  }
}

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfilePanel } from './ProfilePanel';
import { keyboard, mouse } from '../test/fixtures';
import type { SoftwareProfile } from '../profilesApi';

const saved: SoftwareProfile = {
  id: 'a'.repeat(32), name: 'Work', revision: 1, device_id: 'pulsar_susanto_x',
  settings: { kind: 'mouse', dpi: 1600, polling_rate_hz: 500 },
};

describe('software profile editor', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let profiles: SoftwareProfile[];
  beforeEach(() => {
    profiles = [];
    fetchMock = vi.fn(async (path: string, options?: RequestInit) => {
      if (path === '/api/session') return Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 });
      if (path === '/api/profiles' && options?.method === 'GET') return Response.json({ profiles });
      if (path === '/api/profiles' && options?.method === 'POST') {
        const profile = { ...JSON.parse(String(options.body)), id: 'b'.repeat(32), revision: 1 } as SoftwareProfile;
        profiles.push(profile);
        return Response.json(profile, { status: 201 });
      }
      if (path.startsWith('/api/profiles/') && options?.method === 'DELETE') { profiles = []; return Response.json({ deleted: true }); }
      throw new Error('Unexpected request');
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  async function openEditor() {
    fireEvent.click(screen.getByRole('button', { name: 'Manage profiles' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save profile locally' })).toBeEnabled());
  }

  it('does not fetch or apply settings merely by rendering device details', () => {
    render(<ProfilePanel device={mouse} />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Loading or saving a profile never applies/)).toBeVisible();
  });

  it('saves a reviewed mouse draft locally without calling hardware Apply', async () => {
    render(<ProfilePanel device={mouse} />);
    await openEditor();
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'Travel' } });
    fireEvent.change(screen.getByLabelText('DPI (draft)'), { target: { value: '1200' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile locally' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Profile saved locally. No device settings changed.');
    expect(profiles[0].name).toBe('Travel');
    expect(profiles[0].settings).toEqual({ kind: 'mouse', dpi: 1200, polling_rate_hz: 1000 });
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('/apply'))).toBe(false);
  });

  it('loads an existing profile into the draft and deletes only local data', async () => {
    profiles = [saved];
    render(<ProfilePanel device={mouse} />);
    await openEditor();
    fireEvent.change(screen.getByLabelText('Saved profile'), { target: { value: saved.id } });
    expect(screen.getByLabelText('DPI (draft)')).toHaveValue(1600);
    expect(screen.getByLabelText('Polling rate (draft)')).toHaveValue('500');
    expect(screen.getByRole('status')).toHaveTextContent('Profile loaded into the draft. No device settings changed.');
    expect(fetchMock.mock.calls.every(([, options]) => options?.method === 'GET' || options?.method === undefined)).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Delete local profile' }));
    expect(await screen.findByText('Local profile deleted. Device settings were not changed.')).toBeVisible();
    expect(profiles).toEqual([]);
  });

  it('saves RGB intent locally without claiming a successful keyboard write', async () => {
    render(<ProfilePanel device={keyboard} />);
    await openEditor();
    fireEvent.change(screen.getByLabelText('Static RGB color (draft)'), { target: { value: '#123456' } });
    fireEvent.change(screen.getByLabelText('Brightness percent (draft)'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile locally' }));
    await screen.findByText('Profile saved locally. No device settings changed.');
    expect(profiles[0].settings).toEqual({ kind: 'keyboard', rgb: { mode: 'static', color: '#123456', brightness_percent: 30 } });
  });

  it('preserves a draft and shows an error when a revision conflicts', async () => {
    profiles = [saved];
    render(<ProfilePanel device={mouse} />);
    await openEditor();
    fireEvent.change(screen.getByLabelText('Saved profile'), { target: { value: saved.id } });
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'Unsaved edit' } });
    fetchMock.mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(new Response('private error', { status: 409 }));
    fireEvent.click(screen.getByRole('button', { name: 'Save changes locally' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Data changed or is busy. Reload before retrying.');
    expect(screen.getByLabelText('Profile name')).toHaveValue('Unsaved edit');
  });
});

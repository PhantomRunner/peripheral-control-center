import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { StudioSettingsPanel } from './StudioSettingsPanel';
import { DEFAULT_PROFILE } from './studioProfile';
import { keyboard } from '../test/fixtures';

it('imports a local draft without enabling hardware or automatic sync', async () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  const onChange = vi.fn();
  render(<StudioSettingsPanel profile={DEFAULT_PROFILE} onChange={onChange} device={keyboard} stale={false} onUpdated={vi.fn()} />);
  const data = { ...DEFAULT_PROFILE, standbyMinutes: 30, lighting: { ...DEFAULT_PROFILE.lighting, effect: 'breathe' } };
  const file = new File(['profile'], 'studio.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => JSON.stringify(data) });
  fireEvent.change(screen.getByLabelText('Import Studio profile'), { target: { files: [file] } });
  expect(await screen.findByRole('status')).toHaveTextContent('No device settings changed');
  expect(onChange).toHaveBeenCalledWith(data);
  expect(screen.getByRole('checkbox', { name: 'Keep keyboard clock in sync' })).not.toBeChecked();
  expect(screen.getByRole('button', { name: 'Apply standby' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Sync keyboard clock' })).toBeDisabled();
  expect(fetchMock).not.toHaveBeenCalled();
});

it('leaves existing drafts untouched after an invalid import', async () => {
  const onChange = vi.fn(); render(<StudioSettingsPanel profile={DEFAULT_PROFILE} onChange={onChange} device={keyboard} stale={false} onUpdated={vi.fn()} />);
  const file = new File(['broken'], 'broken.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => '{' });
  fireEvent.change(screen.getByLabelText('Import Studio profile'), { target: { files: [file] } });
  expect(await screen.findByRole('alert')).toHaveTextContent('valid JSON');
  expect(onChange).not.toHaveBeenCalled();
});

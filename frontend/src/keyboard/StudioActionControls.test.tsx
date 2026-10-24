import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { StudioActionControls } from './StudioActionControls';
import { keyboard } from '../test/fixtures';
import { localClockTime, StudioClient } from './studioApi';

const intent = { operation: 'standby' as const, minutes: 5 };
const props = { device: keyboard, stale: false, supported: true, intent, label: 'Apply standby', onUpdated: vi.fn() };

it('requires both explicit consents, never writes on mount and reports only matching ACK', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ token: 'x'.repeat(43), expires_in_seconds: 1800 }))
    .mockResolvedValueOnce(Response.json({ device_id: keyboard.id, status: 'acknowledged', requested: intent, actual_settings: null, persistence_verified: false }));
  vi.stubGlobal('fetch', fetchMock);
  render(<StudioActionControls {...props} />);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Other device-control tools are closed for Apply standby' }));
  expect(screen.getByRole('button', { name: 'Apply standby' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Allow device-memory writes for Apply standby' }));
  fireEvent.click(screen.getByRole('button', { name: 'Apply standby' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Standby command acknowledged');
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ intent, vendor_tools_closed: true, allow_device_memory_writes: true });
  expect(screen.getAllByRole('checkbox').every(input => !(input as HTMLInputElement).checked)).toBe(true);
});

it('renews consent after intent/backend/connection changes', () => {
  const { rerender } = render(<StudioActionControls {...props} />);
  for (const checkbox of screen.getAllByRole('checkbox')) fireEvent.click(checkbox);
  rerender(<StudioActionControls {...props} stale />);
  rerender(<StudioActionControls {...props} intent={{ operation: 'standby', minutes: 30 }} />);
  expect(screen.getAllByRole('checkbox').every(input => !(input as HTMLInputElement).checked)).toBe(true);
  expect(screen.getByRole('button', { name: 'Apply standby' })).toBeDisabled();
});

it.each([
  { requested: { operation: 'standby', minutes: 30 } },
  { actual_settings: { minutes: 5 } }, { persistence_verified: true }, { status: 'verified' },
])('does not accept fake readback, persistence or mismatched intent (%#)', async patch => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'x'.repeat(43), expires_in_seconds: 1800 }))
    .mockResolvedValueOnce(Response.json({ device_id: keyboard.id, status: 'acknowledged', requested: intent, actual_settings: null, persistence_verified: false, ...patch })));
  await expect(new StudioClient().apply(intent, true, true)).rejects.toThrow('No matching Studio acknowledgement');
});

it('sends an explicit local timezone with computer clock fields', () => {
  const now = new Date('2026-10-24T12:34:56Z'), value = localClockTime(now);
  expect(value).toMatch(/T\d{2}:\d{2}:56[+-]\d{2}:\d{2}$/);
  expect(Date.parse(value)).toBe(now.getTime());
});

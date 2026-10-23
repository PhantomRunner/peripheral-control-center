import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { KeyboardControl } from './KeyboardControl';
import { keyboard } from '../test/fixtures';

it('requires explicit closure and sends only the protected control-read request', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
    .mockResolvedValueOnce(Response.json({ device_id: keyboard.id, responded: true, recorded_at: '2026-10-23T19:23:29Z' }));
  vi.stubGlobal('fetch', fetchMock);
  const refresh = vi.fn().mockResolvedValue(undefined);
  render(<KeyboardControl device={keyboard} stale={false} onUpdated={refresh} />);
  expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Check wired control' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', { name: 'Check wired control' }));
  expect(await screen.findByRole('status')).toHaveTextContent('wired control interface responded');
  expect(fetchMock.mock.calls[1][0]).toBe('/api/devices/ajazz_ak820_pro/control/read');
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ vendor_tools_closed: true });
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(refresh).toHaveBeenCalledOnce();
});

it.each([true, false])('blocks stale or receiver-only control access (%s)', (stale) => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  render(<KeyboardControl device={stale ? keyboard : { ...keyboard, status: 'receiver_detected', connection: { ...keyboard.connection, wired_usb_present: false } }} stale={stale} onUpdated={vi.fn()} />);
  expect(screen.getByRole('checkbox')).toBeDisabled();
  expect(screen.getByRole('button')).toBeDisabled();
  expect(fetchMock).not.toHaveBeenCalled();
});

it('labels a timestamped response without fabricating RGB/battery/firmware', () => {
  render(<KeyboardControl device={{ ...keyboard, control_responded: true, control_checked_at: '2026-10-23T19:23:29Z' }} stale={false} onUpdated={vi.fn()} />);
  expect(screen.getByText(/Wired control: Responded/)).toBeVisible();
  expect(screen.getByText(/Last control response:/)).toBeVisible();
  expect(screen.getByText(/Battery, firmware and current lighting remain unavailable/)).toBeVisible();
});

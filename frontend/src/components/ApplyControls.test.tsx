import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApplyControls } from './ApplyControls';
import { keyboard, mouse } from '../test/fixtures';
import type { Device } from '../types';

const desired = { kind: 'mouse' as const, dpi: 800, polling_rate_hz: null };
const enabled = { ...mouse, capabilities: { ...mouse.capabilities, settings_write: true } };

function Controls({ device = enabled, stale = false, onUpdated }: { device?: Device; stale?: boolean; onUpdated?: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  return <ApplyControls device={device} desired={desired} stale={stale} busy={busy} onBusy={setBusy} onUpdated={onUpdated} />;
}

describe('explicit hardware Apply', () => {
  it.each([{ device: mouse }, { device: enabled, stale: true }, { device: { ...enabled, status: 'offline' as const } }])('blocks unavailable, stale and offline devices (%#)', (props) => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    render(<Controls {...props} />);
    expect(screen.getByRole('button', { name: 'Apply settings' })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('sends nothing until Apply, then requires matching readback', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ token: 'x'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: mouse.id, status: 'verified', settings: desired }));
    vi.stubGlobal('fetch', fetchMock);
    const refresh = vi.fn().mockResolvedValue(undefined);
    render(<Controls onUpdated={refresh} />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Apply settings' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Other device-control tools are closed for Apply' }));
    fireEvent.click(screen.getByRole('button', { name: 'Apply settings' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Settings applied and verified by device readback.');
    expect(fetchMock.mock.calls[1][0]).toBe(`/api/devices/${mouse.id}/settings/apply`);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ settings: desired, vendor_tools_closed: true });
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('never treats a different readback as success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'x'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: mouse.id, status: 'verified', settings: { ...desired, dpi: 400 } })));
    render(<Controls />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Other device-control tools are closed for Apply' }));
    fireEvent.click(screen.getByRole('button', { name: 'Apply settings' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Readback differs');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('blocks receiver-only keyboards even if an adapter advertises settings support', () => {
    const receiver = { ...keyboard, status: 'receiver_detected' as const, connection: { ...keyboard.connection, wired_usb_present: false }, capabilities: { ...keyboard.capabilities, settings_write: true } };
    render(<ApplyControls device={receiver} desired={{ kind: 'keyboard', rgb: { mode: 'static', color: '#112233', brightness_percent: 60 } }} stale={false} busy={false} onBusy={() => {}} />);
    expect(screen.getByRole('button', { name: 'Apply settings' })).toBeDisabled();
    expect(screen.getByText('Connect the keyboard by USB before applying RGB settings.')).toBeVisible();
  });

  it('rejects values outside the exact tested set before any request', () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    const device = { ...enabled, write_options: { dpi: [800, 1200], polling_rate_hz: [500, 1000], profile_index: 0, active_stage_index: 2, firmware_version: '3.03' } };
    render(<ApplyControls device={device} desired={{ ...desired, dpi: 1600 }} stale={false} busy={false} onBusy={() => {}} />);
    expect(screen.getByRole('button', { name: 'Apply settings' })).toBeDisabled();
    expect(screen.getByRole('checkbox')).toBeDisabled();
    expect(screen.getByText(/outside the verified settings/)).toBeVisible();
    expect(screen.getByText(/Settings may persist in device memory/)).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('requires renewed tool-closure confirmation after changing the draft', () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    const props = { device: enabled, desired, stale: false, busy: false, onBusy: () => {} };
    const { rerender } = render(<ApplyControls {...props} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('button', { name: 'Apply settings' })).toBeEnabled();
    rerender(<ApplyControls {...props} desired={{ ...desired, dpi: 1200 }} />);
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Apply settings' })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TelemetryControls } from './TelemetryControls';
import { DeviceDetails } from './DeviceDetails';
import { mouse } from '../test/fixtures';

const supported = { ...mouse, driver_state: 'read_only' as const, capabilities: { ...mouse.capabilities, battery_read: true, firmware_read: true } };
const reading = { device_id: mouse.id, battery_percent: 20, charging: false, firmware_version: '3.03', recorded_at: '2026-10-23T16:12:11Z' };

describe('manual battery and firmware', () => {
  it('sends nothing on render and requires an explicit tool-closure checkbox', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json(reading));
    vi.stubGlobal('fetch', fetchMock);
    const refresh = vi.fn().mockResolvedValue(undefined);
    render(<TelemetryControls device={supported} stale={false} onUpdated={refresh} />);
    expect(screen.getByRole('button', { name: 'Read battery and firmware' })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Other device-control tools are closed' }));
    fireEvent.click(screen.getByRole('button', { name: 'Read battery and firmware' }));
    expect(await screen.findByRole('status')).toHaveTextContent('read successfully');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/devices/pulsar_susanto_x/telemetry/read');
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ vendor_tools_closed: true });
    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it.each([true, false])('blocks stale or offline hardware (%s)', (stale) => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    render(<TelemetryControls device={stale ? supported : { ...supported, status: 'offline' }} stale={stale} onUpdated={vi.fn()} />);
    expect(screen.getByRole('checkbox')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Read battery and firmware' })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('refreshes after failure to remove readings invalidated by the backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(new Response('private device path', { status: 503 })));
    const refresh = vi.fn().mockResolvedValue(undefined);
    render(<TelemetryControls device={supported} stale={false} onUpdated={refresh} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Read battery and firmware' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Hardware read was not confirmed');
    expect(screen.getByRole('alert')).not.toHaveTextContent('private');
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('shows timestamped readings while keeping unsupported DPI/polling unavailable', () => {
    render(<DeviceDetails device={{ ...supported, battery_percent: 20, firmware_version: '3.03', telemetry_updated_at: reading.recorded_at }} stale={false} />);
    expect(screen.getByText('20%')).toBeVisible();
    expect(screen.getByText('3.03')).toBeVisible();
    expect(screen.getByText(/Last hardware read:/)).toBeVisible();
    expect(screen.getAllByText('—')).toHaveLength(2);
  });
});

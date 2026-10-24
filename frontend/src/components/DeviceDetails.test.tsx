import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DeviceDetails } from './DeviceDetails';
import { keyboard, mouse, offlineMouse } from '../test/fixtures';

describe('device details', () => {
  it('renders independent read capabilities and renews consent after reconnect', () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    const configOnly = { ...mouse, capabilities: { ...mouse.capabilities, dpi_read: true, polling_rate_read: true } };
    const { rerender } = render(<DeviceDetails device={configOnly} stale={false} onTelemetryRead={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Read DPI and polling' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Read battery and firmware' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox'));
    rerender(<DeviceDetails device={{ ...configOnly, status: 'offline' }} stale={false} onTelemetryRead={vi.fn()} />);
    rerender(<DeviceDetails device={configOnly} stale={false} onTelemetryRead={vi.fn()} />);
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    rerender(<DeviceDetails device={mouse} stale={false} onTelemetryRead={vi.fn()} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('distinguishes a receiver from a verified wireless link', () => {
    render(<DeviceDetails device={mouse} stale={false} />);
    const connection = screen.getByRole('region', { name: 'Connection' });
    expect(within(connection).getByText('USB receiver detected')).toBeVisible();
    expect(within(connection).getByText('Not verified')).toBeVisible();
    expect(within(screen.getByRole('region', { name: 'Telemetry' })).getAllByRole('definition').map((el) => el.textContent)).toEqual(['—', '—', '—', '—']);
  });

  it('shows both wired USB and the receiver when both are enumerated', () => {
    render(<DeviceDetails device={keyboard} stale={false} />);
    const connection = screen.getByRole('region', { name: 'Connection' });
    expect(within(connection).getAllByText('Detected')).toHaveLength(2);
    expect(within(connection).getByText('0c45:8009 · 0c45:fdfd')).toBeVisible();
    expect(within(connection).getByText('Not verified')).toBeVisible();
  });

  it('keeps adapter support separate from offline presence and offers no write controls', () => {
    render(<DeviceDetails device={offlineMouse} stale={false} />);
    expect(screen.getByText('USB not detected')).toBeVisible();
    const support = screen.getByRole('region', { name: 'Adapter support' });
    expect(within(support).getByText('Available')).toBeVisible();
    expect(within(support).getAllByText('Not implemented')).toHaveLength(6);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('labels stale presence as last known', () => {
    render(<DeviceDetails device={keyboard} stale />);
    expect(screen.getByText('Last known: Wired USB detected')).toBeVisible();
  });
});

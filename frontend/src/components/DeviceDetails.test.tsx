import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DeviceDetails } from './DeviceDetails';
import { keyboard, mouse, offlineMouse } from '../test/fixtures';

describe('device details', () => {
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
    expect(within(support).getAllByText('Not implemented')).toHaveLength(5);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('labels stale presence as last known', () => {
    render(<DeviceDetails device={keyboard} stale />);
    expect(screen.getByText('Last known: Wired USB detected')).toBeVisible();
  });
});

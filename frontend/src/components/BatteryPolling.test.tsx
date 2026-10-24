import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BatteryPolling } from './BatteryPolling';
import { DeviceDetails } from './DeviceDetails';
import { mouse } from '../test/fixtures';

const supported = { ...mouse, capabilities: { ...mouse.capabilities, battery_read: true, firmware_read: true } };
const snapshot = { device_id: mouse.id, battery_percent: 20, charging: false, firmware_version: '3.03', recorded_at: '2026-10-24T12:51:29Z' };
const refresh = vi.fn().mockResolvedValue(undefined);

function fakeNetwork() {
  const fetchMock = vi.fn().mockImplementation(async (input) => Response.json(input === '/api/session'
    ? { token: 'a'.repeat(43), expires_in_seconds: 1800 } : snapshot));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function start() {
  fireEvent.click(screen.getByRole('checkbox', { name: 'Other device-control tools stay closed while polling' }));
  fireEvent.click(screen.getByRole('button', { name: 'Start battery polling' }));
  await act(async () => {});
}

describe('opt-in conservative battery polling', () => {
  beforeEach(() => { vi.useFakeTimers(); refresh.mockClear(); });

  it('does no IO by default, waits 60 seconds and schedules from completion', async () => {
    const fetchMock = fakeNetwork();
    render(<BatteryPolling device={supported} stale={false} onUpdated={refresh} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Start battery polling' })).toBeDisabled();
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(59_999); });
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetchMock.mock.calls.map(([input]) => input)).toEqual(['/api/session', '/api/devices/pulsar_susanto_x/telemetry/poll']);
    expect(refresh).toHaveBeenCalledOnce();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    fireEvent.click(screen.getByRole('button', { name: 'Stop battery polling' }));
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it('never overlaps a slow request and Stop does not replay its completion', async () => {
    let finish!: (value: Response) => void;
    const fetchMock = fakeNetwork();
    fetchMock.mockImplementationOnce(async () => Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    render(<BatteryPolling device={supported} stale={false} onUpdated={refresh} />);
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(screen.getByText('Reading battery…')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Stop battery polling' }));
    expect(screen.getByRole('button', { name: 'Start battery polling' })).toBeDisabled();
    await act(async () => { finish(Response.json(snapshot)); });
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('status')).toHaveTextContent('Polling stopped');
  });

  it('waits a full minute after a slow read finishes before the next read', async () => {
    let finish!: (value: Response) => void;
    const fetchMock = fakeNetwork();
    fetchMock.mockImplementationOnce(async () => Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    render(<BatteryPolling device={supported} stale={false} onUpdated={refresh} />);
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(65_000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => { finish(Response.json(snapshot)); });
    await act(async () => { await vi.advanceTimersByTimeAsync(59_999); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it.each([503, 423, 429])('stops after HTTP %s without retrying and refreshes invalidated data', async (status) => {
    const fetchMock = fakeNetwork();
    fetchMock.mockImplementationOnce(async () => Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockImplementationOnce(async () => new Response('private device path', { status }));
    render(<BatteryPolling device={supported} stale={false} onUpdated={refresh} />);
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(screen.getByRole('alert')).toHaveTextContent('Polling stopped');
    expect(screen.getByRole('alert')).not.toHaveTextContent('private');
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('stops after a stalled network request instead of restarting a timer', async () => {
    const fetchMock = fakeNetwork();
    fetchMock.mockImplementationOnce(async () => Response.json({ token: 'a'.repeat(43), expires_in_seconds: 1800 }))
      .mockImplementationOnce((_input, init) => new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
      }));
    render(<BatteryPolling device={supported} stale={false} onUpdated={refresh} />);
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(68_000); });
    expect(screen.getByRole('alert')).toHaveTextContent('Polling stopped. Request timed out');
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('stops on hidden page and does not resume automatically', async () => {
    const fetchMock = fakeNetwork();
    render(<BatteryPolling device={supported} stale={false} onUpdated={refresh} />);
    await start();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    fireEvent(document, new Event('visibilitychange'));
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    fireEvent(document, new Event('visibilitychange'));
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Start battery polling' })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(['disconnect', 'backend', 'capability'] as const)('stops when %s changes and does not resume on recovery', async (reason) => {
    const fetchMock = fakeNetwork();
    const { rerender, unmount } = render(<DeviceDetails device={supported} stale={false} onTelemetryRead={refresh} />);
    await start();
    const changed = reason === 'disconnect' ? { ...supported, status: 'offline' as const }
      : reason === 'capability' ? mouse : supported;
    rerender(<DeviceDetails device={changed} stale={reason === 'backend'} onTelemetryRead={refresh} />);
    rerender(<DeviceDetails device={supported} stale={false} onTelemetryRead={refresh} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    const group = screen.getByRole('group', { name: 'Battery polling' });
    expect(within(group).getByRole('checkbox')).not.toBeChecked();
    expect(fetchMock).not.toHaveBeenCalled();
    await start();
    unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

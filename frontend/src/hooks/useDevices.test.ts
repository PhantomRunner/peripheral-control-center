import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useDevices } from './useDevices';
import { deviceResponse, pendingRequest } from '../test/fixtures';

describe('device refresh lifecycle', () => {
  beforeEach(() => { vi.useFakeTimers(); });

  it('refreshes USB discovery every 15 seconds', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => deviceResponse());
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useDevices());
    await act(async () => {});
    expect(result.current.devices).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(14_999); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.refreshing).toBe(false);
  });

  it('does not overlap manual refresh requests', async () => {
    const fetchMock = vi.fn(pendingRequest);
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useDevices());
    await act(async () => { await result.current.refresh(); await result.current.refresh(); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.refreshing).toBe(true);
  });

  it('times out a stalled request and allows a successful retry', async () => {
    const fetchMock = vi.fn().mockImplementationOnce(pendingRequest).mockResolvedValueOnce(deviceResponse());
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useDevices());
    await act(async () => { await vi.advanceTimersByTimeAsync(8_000); });
    expect(result.current.error).toBe('The local backend did not respond in time.');
    expect(result.current.refreshing).toBe(false);
    expect(result.current.devices).toBeNull();
    await act(async () => { await result.current.refresh(); });
    expect(result.current.devices).toHaveLength(2);
    expect(result.current.error).toBeNull();
  });

  it('aborts in-flight work and clears polling on unmount', async () => {
    const fetchMock = vi.fn(pendingRequest);
    vi.stubGlobal('fetch', fetchMock);
    const { unmount } = renderHook(() => useDevices());
    const signal = fetchMock.mock.calls[0][1]?.signal;
    await act(async () => { unmount(); });
    expect(signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('queues a fresh enumeration after an existing request when manual telemetry finishes', async () => {
    let finish!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { finish = resolve; });
    const fetchMock = vi.fn().mockReturnValueOnce(pending).mockImplementation(async () => deviceResponse());
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useDevices());
    await act(async () => { await result.current.refresh(); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { finish(deviceResponse()); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.devices).toHaveLength(2);
  });
});

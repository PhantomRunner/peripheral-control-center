import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchDevices } from '../api';
import type { Device } from '../types';

type DeviceState = {
  devices: Device[] | null;
  error: string | null;
  refreshing: boolean;
  lastChecked: Date | null;
  disconnected: string[];
};

export function useDevices() {
  const [state, setState] = useState<DeviceState>({
    devices: null, error: null, refreshing: true, lastChecked: null, disconnected: [],
  });
  const inFlight = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    const controller = new AbortController();
    inFlight.current = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 8_000);
    setState((previous) => ({ ...previous, refreshing: true }));
    try {
      const devices = await fetchDevices(controller.signal);
      if (controller.signal.aborted) return;
      setState((previous) => ({
        devices, error: null, refreshing: false, lastChecked: new Date(),
        disconnected: (previous.devices ?? []).filter((old) =>
          old.status !== 'offline'
          && !devices.some((current) => current.id === old.id && current.status !== 'offline'),
        ).map((device) => device.name),
      }));
    } catch (cause) {
      if (controller.signal.aborted && !timedOut) return;
      setState((previous) => ({
        ...previous, refreshing: false,
        error: timedOut ? 'The local backend did not respond in time.'
          : cause instanceof Error ? cause.message : 'Cannot reach the local backend.',
      }));
    } finally {
      window.clearTimeout(timeout);
      if (inFlight.current === controller) inFlight.current = null;
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => { void refresh(); }, 15_000);
    return () => {
      window.clearInterval(interval);
      inFlight.current?.abort();
      inFlight.current = null;
    };
  }, [refresh]);

  return { ...state, refresh, stale: state.devices !== null && state.error !== null };
}

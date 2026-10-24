import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useScreenTransfer } from './useScreenTransfer';
import { ScreenClient } from './screenApi';
import { ScreenUploadControls } from './ScreenUploadControls';
import { keyboard } from '../test/fixtures';

const frame = { rgb565: new Uint8Array(32768), rgba: new Uint8ClampedArray(), delayMs: 0 };
const job = { id: 'a'.repeat(32), status: 'running', frame_count: 1, total_blocks: 9, actual_settings: null, persistence_verified: false, detail: null };
const token = { token: 't'.repeat(43), expires_in_seconds: 1800 };
beforeEach(() => { vi.useFakeTimers(); });

it('starts once with semantic pixels and checks job status without repeating a write', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(token)).mockResolvedValueOnce(Response.json(job))
    .mockResolvedValueOnce(Response.json({ ...job, status: 'transfer_completed' }));
  vi.stubGlobal('fetch', fetchMock);
  const { result } = renderHook(() => useScreenTransfer());
  expect(fetchMock).not.toHaveBeenCalled();
  await act(async () => { await result.current.start([frame]); });
  expect(result.current.busy).toBe(true);
  const body = JSON.parse(fetchMock.mock.calls[1][1].body);
  expect(Object.keys(body)).toEqual(['frames','vendor_tools_closed','allow_device_memory_writes']);
  expect(body.frames[0].rgb565_base64).toHaveLength(43692);
  await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
  expect(result.current.job?.status).toBe('transfer_completed');
  expect(result.current.busy).toBe(false);
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(fetchMock.mock.calls[2][1].method).toBe('GET');
});

it('stops status polling on error and permits an explicit metadata-only recovery', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(token)).mockResolvedValueOnce(Response.json(job))
    .mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(Response.json({ ...job,status:'transfer_completed' }));
  vi.stubGlobal('fetch', fetchMock);
  const { result } = renderHook(() => useScreenTransfer());
  await act(async () => { await result.current.start([frame]); await vi.advanceTimersByTimeAsync(2_000); });
  expect(result.current.error).toContain('may still finish');
  expect(result.current.busy).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(fetchMock).toHaveBeenCalledTimes(3);
  await act(async () => { await result.current.refreshStatus(); });
  expect(result.current.job?.status).toBe('transfer_completed');
  expect(result.current.error).toBeNull();
  expect(fetchMock.mock.calls.filter(([,options]) => options.method === 'POST')).toHaveLength(1);
});

it('clears status timers on unmount without starting another transfer', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(token)).mockResolvedValueOnce(Response.json(job));
  vi.stubGlobal('fetch', fetchMock);
  const { result, unmount } = renderHook(() => useScreenTransfer());
  await act(async () => { await result.current.start([frame]); });
  unmount(); await vi.advanceTimersByTimeAsync(60_000);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it('requires tool and overwrite consent and resets them immediately after starting', async () => {
  const transfer = { job:null,starting:false,error:null,busy:false,start:vi.fn().mockResolvedValue(undefined),refreshStatus:vi.fn() };
  const device = { ...keyboard,studio_capabilities:{ lighting_effects:true,clock_write:true,standby_write:true,screen_write:true,max_screen_frames:120 } };
  render(<ScreenUploadControls device={device} stale={false} frames={[frame]} preparing={false} transfer={transfer} />);
  const button = screen.getByRole('button',{name:'Send screen to keyboard'});
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox',{name:'Other device-control tools are closed for screen upload'}));
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow replacing the TFT image and writing device memory'}));
  fireEvent.click(button);
  await act(async () => {});
  expect(transfer.start).toHaveBeenCalledOnce();
  expect(screen.getAllByRole('checkbox').every(input => !(input as HTMLInputElement).checked)).toBe(true);
});

it.each([{total_blocks:8},{frame_count:0},{actual_settings:{}},{persistence_verified:true},{id:'private/path'}])('rejects inconsistent or fabricated transfer status (%#)', async patch => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(Response.json(token)).mockResolvedValueOnce(Response.json({...job,...patch})));
  await expect(new ScreenClient().start([frame],true,true)).rejects.toThrow();
});

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScreenClient, type ScreenJob } from './screenApi';
import type { ScreenFrame } from './screenMedia';

export function useScreenTransfer() {
  const [job, setJob] = useState<ScreenJob | null>(null), [starting, setStarting] = useState(false), [error, setError] = useState<string | null>(null);
  const client = useMemo(() => new ScreenClient(), []);
  const alive = useRef(true), timer = useRef<number | null>(null), running = useRef(false), startedAt = useRef(0);
  const activeId = useRef<string | null>(null), checking = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; if (timer.current !== null) window.clearTimeout(timer.current); }; }, []);
  const check = useCallback(async (id: string): Promise<void> => {
    if (checking.current) return;
    checking.current = true;
    try {
      const result = await client.status(id);
      if (!alive.current || activeId.current !== id) return;
      setJob(result); setError(null);
      if (result.status === 'running') {
        if (Date.now() - startedAt.current > 320_000) { setError('Transfer status is still uncertain. Check the keyboard; do not start another upload blindly.'); return; }
        timer.current = window.setTimeout(() => { void check(id); }, 2_000);
      } else running.current = false;
    } catch {
      if (alive.current && activeId.current === id) setError('Transfer status is unavailable. The upload may still finish. Refresh its status before starting another.');
    } finally { checking.current = false; }
  }, [client]);
  const start = async (frames: ScreenFrame[]) => {
    if (running.current) return false;
    running.current = true; activeId.current = null; startedAt.current = Date.now(); setStarting(true); setError(null); setJob(null);
    if (timer.current !== null) window.clearTimeout(timer.current);
    try {
      const result = await client.start(frames, true, true);
      if (!alive.current) return false;
      activeId.current = result.id;
      setJob(result);
      if (result.status === 'running') timer.current = window.setTimeout(() => { void check(result.id); }, 2_000);
      else running.current = false;
      return result.status !== 'failed';
    } catch (cause) {
      running.current = false;
      if (alive.current) setError(`${cause instanceof Error ? cause.message : 'Upload start was not confirmed.'} Check the keyboard before retrying; a request already accepted may still finish.`);
      return false;
    } finally { if (alive.current) setStarting(false); }
  };
  const refreshStatus = async () => {
    if (!job) return;
    if (timer.current !== null) window.clearTimeout(timer.current);
    await check(job.id);
  };
  return { job, starting, error, start, refreshStatus, busy: starting || job?.status === 'running' };
}

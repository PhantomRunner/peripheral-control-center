"""Single owned asynchronous screen transfer; status checks never perform HID IO."""
import secrets
import threading
import time
from collections.abc import Callable
from typing import Literal, Protocol

from pcc.settings import StrictModel
from pcc.screen_models import ScreenApplyRequest, ScreenIntent, artwork_payload
from pcc.studio_service import StudioService, StudioBusy, StudioUnavailable


class ScreenJob(StrictModel):
    id: str
    status: Literal['running','transfer_completed','failed']
    frame_count: int
    total_blocks: int
    actual_settings: None = None
    persistence_verified: Literal[False] = False
    detail: str | None = None


class ScreenAdapter(Protocol):
    validation_reference: str
    def apply(self, intent: ScreenIntent) -> None: ...


def background(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True, name='pcc-screen-transfer').start()


class ScreenJobs:
    def __init__(self, control: StudioService, adapter: ScreenAdapter, executor: Callable = background, clock: Callable[[], float] = time.monotonic):
        self.control, self.adapter, self.executor, self.clock = control, adapter, executor, clock
        self.lock = threading.Lock()
        self.jobs: dict[str, tuple[str,float,ScreenJob]] = {}

    def start(self, request: ScreenApplyRequest, origin: str) -> ScreenJob:
        self.control.authorize(request.vendor_tools_closed, request.allow_device_memory_writes)
        if not self.adapter.validation_reference: raise StudioUnavailable
        if not self.control.operation_lock.acquire(blocking=False): raise StudioBusy
        try:
            intent = ScreenIntent(frames=request.frames)
            job = ScreenJob(id=secrets.token_hex(16),status='running',frame_count=len(intent.frames),total_blocks=len(artwork_payload(intent)) // 4096)
            with self.lock:
                self.jobs = {key:value for key,value in self.jobs.items() if value[2].status == 'running' or self.clock() - value[1] < 600}
                if len(self.jobs) >= 8: self.jobs.pop(next(iter(self.jobs)))
                self.jobs[job.id] = (origin,self.clock(),job)
            def work():
                try:
                    self.adapter.apply(intent)
                    result = job.model_copy(update={'status':'transfer_completed'})
                except Exception:
                    result = job.model_copy(update={'status':'failed','detail':'Screen transfer was not confirmed. Artwork may have changed; check before retrying.'})
                finally:
                    self.control.operation_lock.release()
                with self.lock: self.jobs[job.id] = (origin,self.clock(),result)
            self.executor(work)
            return job
        except Exception:
            self.control.operation_lock.release()
            raise

    def get(self, job_id: str, origin: str) -> ScreenJob | None:
        with self.lock:
            found = self.jobs.get(job_id)
            if found is None or found[0] != origin or (found[2].status != 'running' and self.clock() - found[1] >= 600): return None
            return found[2]

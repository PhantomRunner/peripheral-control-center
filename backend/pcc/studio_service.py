"""Serialize explicitly requested Studio operations; discovery never writes."""
import threading
from typing import Protocol

from pcc.drivers import registry
from pcc.studio_models import StudioApplyRequest, StudioApplyResult, StudioIntent


class StudioUnavailable(Exception): pass
class StudioBusy(Exception): pass
class StudioOperationFailed(Exception): pass


class StudioAdapter(Protocol):
    validation_reference: str
    def apply(self, intent: StudioIntent) -> None: ...


class StudioService:
    def __init__(self, adapter: StudioAdapter):
        self.adapter = adapter
        self.operation_lock = threading.Lock()

    def authorize(self, tools_closed: bool, memory_allowed: bool) -> None:
        if tools_closed is not True or memory_allowed is not True or not self.adapter.validation_reference:
            raise StudioUnavailable('Confirm tool closure and device-memory writes.')
        if not any(d.id == 'ajazz_ak820_pro' and d.connection.wired_usb_present for d in registry.discover_devices()):
            raise StudioUnavailable('Studio writes require the wired keyboard.')

    def apply(self, request: StudioApplyRequest) -> StudioApplyResult:
        self.authorize(request.vendor_tools_closed, request.allow_device_memory_writes)
        if not self.operation_lock.acquire(blocking=False): raise StudioBusy
        try:
            self.adapter.apply(request.intent)
            return StudioApplyResult(requested=request.intent)
        except (OSError, RuntimeError):
            raise StudioOperationFailed('Studio operation failed; settings may have changed.') from None
        finally: self.operation_lock.release()

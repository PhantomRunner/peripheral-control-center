"""Semantic performance API. Unvalidated operations reject before hardware IO."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .drivers.pulsar_performance import PerformanceUnavailable, apply_performance, read_performance
from .performance_models import PerformanceApplyRequest, PerformanceApplyResult, PerformanceCapabilities, PerformanceReadRequest, PerformanceSnapshot, validate_apply_context
from .performance_support import validate_action, validated_capabilities
from .telemetry import TelemetryBusy, TelemetryService, TelemetryUnavailable
from .telemetry_api import get_telemetry_service

router = APIRouter(prefix='/api/devices/pulsar_susanto_x/performance')


class PerformanceService:
    def __init__(self, reader: Callable[[], PerformanceSnapshot] = read_performance,
                 capabilities: PerformanceCapabilities | None = None,
                 writer: Callable[[PerformanceApplyRequest],PerformanceSnapshot] = apply_performance):
        self.reader = reader
        # No runtime/environment switch can enable unvalidated hardware writes.
        self.capabilities = capabilities or validated_capabilities()
        self.writer = writer

    def read(self, body: PerformanceReadRequest, telemetry: TelemetryService) -> PerformanceSnapshot:
        if not body.vendor_tools_closed or not self.capabilities.snapshot_read:
            raise HTTPException(409, 'Performance reading is unavailable or tool closure is unconfirmed.')
        try:
            with telemetry.pulsar_operation():
                snapshot = self.reader()
            return snapshot
        except TelemetryBusy:
            raise HTTPException(423, 'The device is busy.') from None
        except (TelemetryUnavailable, PerformanceUnavailable, OSError, ValueError):
            raise HTTPException(503, 'Performance read was not confirmed. No retry was sent.') from None

    def apply(self, body: PerformanceApplyRequest, telemetry: TelemetryService) -> PerformanceApplyResult:
        if not body.vendor_tools_closed or not body.allow_device_memory_writes:
            raise HTTPException(409,'Explicit tool-closure and device-memory consent required.')
        try:
            validate_action(body.action,self.capabilities)
        except ValueError:
            raise HTTPException(409,'This performance write or value is not validated.') from None
        telemetry.invalidate_config()
        try:
            with telemetry.pulsar_operation():
                actual = self.writer(body)
                validate_apply_context(body,actual)
            return PerformanceApplyResult(requested=body.action,actual=actual)
        except TelemetryBusy:
            raise HTTPException(423,'The device is busy.') from None
        except (TelemetryUnavailable,PerformanceUnavailable,OSError,ValueError):
            raise HTTPException(502,'Readback did not verify the operation. State may have changed; no retry was sent.') from None
        finally:
            telemetry.invalidate_config()


_service = PerformanceService()


def get_performance_service() -> PerformanceService:
    return _service


@router.post('/read', response_model=PerformanceSnapshot)
def read(body: PerformanceReadRequest, service: Annotated[PerformanceService, Depends(get_performance_service)],
         telemetry: Annotated[TelemetryService, Depends(get_telemetry_service)]) -> PerformanceSnapshot:
    return service.read(body, telemetry)


@router.post('/apply',response_model=PerformanceApplyResult)
def apply(body: PerformanceApplyRequest,service:Annotated[PerformanceService,Depends(get_performance_service)],
          telemetry:Annotated[TelemetryService,Depends(get_telemetry_service)]) -> PerformanceApplyResult:
    return service.apply(body,telemetry)

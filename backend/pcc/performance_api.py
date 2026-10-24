"""Semantic performance API. Unvalidated operations reject before hardware IO."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .drivers.pulsar_performance import PerformanceUnavailable, read_performance
from .performance_models import PerformanceCapabilities, PerformanceReadRequest, PerformanceSnapshot
from .telemetry import TelemetryBusy, TelemetryService, TelemetryUnavailable
from .telemetry_api import get_telemetry_service

router = APIRouter(prefix='/api/devices/pulsar_susanto_x/performance')


class PerformanceService:
    def __init__(self, reader: Callable[[], PerformanceSnapshot] = read_performance,
                 capabilities: PerformanceCapabilities | None = None):
        self.reader = reader
        # No runtime/environment switch can enable unvalidated hardware writes.
        self.capabilities = capabilities or PerformanceCapabilities()

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


_service = PerformanceService()


def get_performance_service() -> PerformanceService:
    return _service


@router.post('/read', response_model=PerformanceSnapshot)
def read(body: PerformanceReadRequest, service: Annotated[PerformanceService, Depends(get_performance_service)],
         telemetry: Annotated[TelemetryService, Depends(get_telemetry_service)]) -> PerformanceSnapshot:
    return service.read(body, telemetry)

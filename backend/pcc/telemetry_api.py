"""Protected explicit hardware reads; no background polling or settings operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .telemetry import ReadTelemetryRequest, TelemetryBusy, TelemetryConsentRequired, TelemetryService, TelemetrySnapshot, TelemetryUnavailable

router = APIRouter(prefix="/api/devices")
_service = TelemetryService()


def get_telemetry_service() -> TelemetryService:
    return _service


@router.post("/pulsar_susanto_x/telemetry/read", response_model=TelemetrySnapshot)
def read_pulsar_telemetry(body: ReadTelemetryRequest, service: Annotated[TelemetryService, Depends(get_telemetry_service)]) -> TelemetrySnapshot:
    try:
        return service.read(vendor_tools_closed=body.vendor_tools_closed)
    except TelemetryConsentRequired:
        raise HTTPException(409, "Close other device-control tools before reading.") from None
    except TelemetryBusy:
        raise HTTPException(423, "A hardware read is already running.") from None
    except TelemetryUnavailable:
        raise HTTPException(503, "Battery/firmware read was not confirmed. Check device access and close other control tools.") from None

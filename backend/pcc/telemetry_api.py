"""Protected explicit hardware reads; no background polling or settings operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .config_telemetry import ConfigSnapshot
from .keyboard_control import ControlSnapshot
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


@router.post("/pulsar_susanto_x/settings/read", response_model=ConfigSnapshot)
def read_pulsar_config(body: ReadTelemetryRequest, service: Annotated[TelemetryService, Depends(get_telemetry_service)]) -> ConfigSnapshot:
    try:
        return service.read_config(vendor_tools_closed=body.vendor_tools_closed)
    except TelemetryConsentRequired:
        raise HTTPException(409, "Close other device-control tools before reading.") from None
    except TelemetryBusy:
        raise HTTPException(423, "A hardware read is already running.") from None
    except TelemetryUnavailable:
        raise HTTPException(503, "DPI/polling read was not confirmed. Check device access and close other control tools.") from None


@router.post("/ajazz_ak820_pro/control/read", response_model=ControlSnapshot)
def read_keyboard_control(body: ReadTelemetryRequest, service: Annotated[TelemetryService, Depends(get_telemetry_service)]) -> ControlSnapshot:
    try:
        return service.read_control(vendor_tools_closed=body.vendor_tools_closed)
    except TelemetryConsentRequired:
        raise HTTPException(409, "Close other device-control tools before reading.") from None
    except TelemetryBusy:
        raise HTTPException(423, "A hardware read is already running.") from None
    except TelemetryUnavailable:
        raise HTTPException(503, "Wired control response was not confirmed. Check the USB cable and close control tools.") from None

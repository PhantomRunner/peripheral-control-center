"""Typed explicit Apply endpoint, protected by the global session middleware."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException

from .apply_settings import ApplyRequest, InvalidSettingsError, RgbAcknowledgement, SettingsOperationError, SettingsService, SettingsUnavailableError, SettingsVerificationError
from .ownership import DeviceBusyError, OwnershipUnavailableError
from .drivers.pulsar_settings import PulsarSettingsAdapter
from .drivers.ajazz_rgb import AjazzRgbAdapter
from .settings import DeviceId, KeyboardSettings, SettingsIntent, StrictModel
from .telemetry import TelemetryService
from .telemetry_api import get_telemetry_service

router = APIRouter(prefix="/api/devices")
_service = SettingsService({"pulsar_susanto_x": PulsarSettingsAdapter()}, ack_rgb_adapters={"ajazz_ak820_pro": AjazzRgbAdapter()})


def get_settings_service() -> SettingsService:
    return _service


class ApplyResult(StrictModel):
    device_id: DeviceId
    status: Literal["verified"] = "verified"
    settings: SettingsIntent


class AcknowledgedApplyResult(StrictModel):
    device_id: Literal["ajazz_ak820_pro"] = "ajazz_ak820_pro"
    status: Literal["acknowledged"] = "acknowledged"
    requested_settings: KeyboardSettings
    actual_settings: None = None
    feedback: Literal["command_acknowledgements"] = "command_acknowledgements"
    readback_available: Literal[False] = False
    persistence_verified: Literal[False] = False
    may_persist: Literal[True] = True


@router.post("/{device_id}/settings/apply", response_model=ApplyResult | AcknowledgedApplyResult)
def apply_settings(device_id: DeviceId, body: ApplyRequest, service: Annotated[SettingsService, Depends(get_settings_service)], telemetry: Annotated[TelemetryService, Depends(get_telemetry_service)]) -> ApplyResult | AcknowledgedApplyResult:
    try:
        actual = service.apply(device_id, body.settings, vendor_tools_closed=body.vendor_tools_closed,
                               allow_device_memory_writes=body.allow_device_memory_writes)
        if isinstance(actual, RgbAcknowledgement):
            return AcknowledgedApplyResult(requested_settings=actual.requested)
        return ApplyResult(device_id=device_id, settings=actual)
    except SettingsUnavailableError:
        raise HTTPException(409, "Settings operation is unavailable. Please confirm other control tools are closed and allow device-memory writes.") from None
    except InvalidSettingsError:
        raise HTTPException(422, "Settings are not supported by this adapter.") from None
    except DeviceBusyError:
        raise HTTPException(423, "Device is already in use by PCC.") from None
    except OwnershipUnavailableError:
        raise HTTPException(503, "Device ownership could not be established.") from None
    except SettingsVerificationError:
        raise HTTPException(502, "Readback did not verify the write. Device state may have changed.") from None
    except SettingsOperationError:
        raise HTTPException(502, "Device operation failed. State may have changed; check it before retrying.") from None
    finally:
        if device_id == "pulsar_susanto_x":
            telemetry.invalidate_config()

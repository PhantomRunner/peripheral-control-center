"""Typed explicit Apply endpoint, protected by the global session middleware."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException

from .apply_settings import ApplyRequest, InvalidSettingsError, SettingsOperationError, SettingsService, SettingsUnavailableError, SettingsVerificationError
from .ownership import DeviceBusyError, OwnershipUnavailableError
from .drivers.pulsar_settings import PulsarSettingsAdapter
from .settings import DeviceId, SettingsIntent, StrictModel
from .telemetry import TelemetryService
from .telemetry_api import get_telemetry_service

router = APIRouter(prefix="/api/devices")
_service = SettingsService({"pulsar_susanto_x": PulsarSettingsAdapter()})


def get_settings_service() -> SettingsService:
    return _service


class ApplyResult(StrictModel):
    device_id: DeviceId
    status: Literal["verified"] = "verified"
    settings: SettingsIntent


@router.post("/{device_id}/settings/apply", response_model=ApplyResult)
def apply_settings(device_id: DeviceId, body: ApplyRequest, service: Annotated[SettingsService, Depends(get_settings_service)], telemetry: Annotated[TelemetryService, Depends(get_telemetry_service)]) -> ApplyResult:
    try:
        actual = service.apply(device_id, body.settings, vendor_tools_closed=body.vendor_tools_closed)
        return ApplyResult(device_id=device_id, settings=actual)
    except SettingsUnavailableError:
        raise HTTPException(409, "Settings operation is unavailable. Check support and confirm other control tools are closed.") from None
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

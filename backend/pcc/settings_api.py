"""Typed explicit Apply endpoint, protected by the global session middleware."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException

from .apply_settings import ApplyRequest, InvalidSettingsError, SettingsOperationError, SettingsService, SettingsUnavailableError, SettingsVerificationError
from .ownership import DeviceBusyError, OwnershipUnavailableError
from .settings import DeviceId, SettingsIntent, StrictModel

router = APIRouter(prefix="/api/devices")
_service = SettingsService()  # Intentionally no live writers registered.


def get_settings_service() -> SettingsService:
    return _service


class ApplyResult(StrictModel):
    device_id: DeviceId
    status: Literal["verified"] = "verified"
    settings: SettingsIntent


@router.post("/{device_id}/settings/apply", response_model=ApplyResult)
def apply_settings(device_id: DeviceId, body: ApplyRequest, service: Annotated[SettingsService, Depends(get_settings_service)]) -> ApplyResult:
    try:
        actual = service.apply(device_id, body.settings)
        return ApplyResult(device_id=device_id, settings=actual)
    except SettingsUnavailableError:
        raise HTTPException(409, "No validated settings operation is enabled for this device.") from None
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

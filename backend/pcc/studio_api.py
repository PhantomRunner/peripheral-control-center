"""Same-origin protected semantic Studio API; no arbitrary HID command endpoint."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException

from pcc.drivers.ajazz_studio import AjazzStudioAdapter
from pcc.studio_models import StudioApplyRequest, StudioApplyResult
from pcc.studio_service import StudioService, StudioBusy, StudioUnavailable, StudioOperationFailed

router = APIRouter(prefix='/api/devices/ajazz_ak820_pro/studio')
_service = StudioService(AjazzStudioAdapter())


def get_studio_service() -> StudioService: return _service


@router.post('/apply', response_model=StudioApplyResult)
def apply(request: StudioApplyRequest, service: Annotated[StudioService, Depends(get_studio_service)]) -> StudioApplyResult:
    try: return service.apply(request)
    except StudioUnavailable: raise HTTPException(409, 'Connect the wired keyboard and confirm tool closure and device-memory writes.') from None
    except StudioBusy: raise HTTPException(423, 'A Studio operation is already running.') from None
    except StudioOperationFailed: raise HTTPException(502, 'Studio command was not confirmed. Settings may have changed; do not retry blindly.') from None

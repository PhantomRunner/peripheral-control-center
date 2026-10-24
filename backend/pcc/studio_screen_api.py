from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from pcc.drivers.ajazz_screen import AjazzScreenAdapter
from pcc.screen_models import MAX_REQUEST_BYTES, ScreenApplyRequest
from pcc.screen_jobs import ScreenJob, ScreenJobs
from pcc.security import local_origin
from pcc.studio_api import get_studio_service
from pcc.studio_service import StudioBusy, StudioUnavailable

router = APIRouter(prefix='/api/devices/ajazz_ak820_pro/studio/screen')
_jobs = ScreenJobs(get_studio_service(), AjazzScreenAdapter())


def get_screen_jobs() -> ScreenJobs: return _jobs


async def read_artwork(request: Request) -> ScreenApplyRequest:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, 'Screen artwork exceeds the request limit.')
        content.extend(chunk)
    try: return ScreenApplyRequest.model_validate_json(bytes(content))
    except ValidationError:
        raise HTTPException(422, 'Invalid or oversized RGB565 artwork. Use 1–120 complete 128×128 frames.') from None


@router.post('/jobs', response_model=ScreenJob, status_code=202)
def start(request: Request, body: Annotated[ScreenApplyRequest, Depends(read_artwork)], jobs: Annotated[ScreenJobs, Depends(get_screen_jobs)]) -> ScreenJob:
    try: return jobs.start(body, local_origin(request, required=True))
    except StudioUnavailable: raise HTTPException(409, 'Connect the wired keyboard and confirm tool closure and device-memory writes.') from None
    except StudioBusy: raise HTTPException(423, 'A keyboard operation is already running.') from None


@router.get('/jobs/{job_id}', response_model=ScreenJob)
def status(job_id: str, request: Request, jobs: Annotated[ScreenJobs, Depends(get_screen_jobs)]) -> ScreenJob:
    origin = local_origin(request, required=False)
    result = jobs.get(job_id, origin)
    if result is None: raise HTTPException(404, 'Screen job is unavailable; check the keyboard before retrying.')
    return result

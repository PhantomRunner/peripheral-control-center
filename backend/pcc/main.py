"""Local discovery, profiles and protected explicit validated-device operations."""

from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .models import DeviceList
from .security import LocalSession, LocalSessionMiddleware, SessionStore, local_origin
from .profile_api import router as profile_router
from .settings_api import router as settings_router
from .telemetry import TelemetryService
from .telemetry_api import get_telemetry_service, router as telemetry_router
from .studio_api import router as studio_router
from .studio_screen_api import router as screen_router

app = FastAPI(title="Peripheral Control Center API", version="0.1.0")
sessions = SessionStore()
app.add_middleware(LocalSessionMiddleware, sessions=sessions)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1"],
)
app.include_router(profile_router)
app.include_router(settings_router)
app.include_router(telemetry_router)
app.include_router(studio_router)
app.include_router(screen_router)


@app.get("/api/session", response_model=LocalSession)
def get_session(request: Request) -> LocalSession:
    return sessions.issue(local_origin(request, required=False))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/devices", response_model=DeviceList)
def get_devices(service: Annotated[TelemetryService, Depends(get_telemetry_service)]) -> DeviceList:
    return DeviceList(devices=service.summaries())

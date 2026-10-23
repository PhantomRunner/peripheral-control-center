"""Local-only read-only API. No firmware or settings operations."""

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .models import DeviceList
from .drivers.registry import discover_devices
from .security import LocalSession, LocalSessionMiddleware, SessionStore, local_origin

app = FastAPI(title="Peripheral Control Center API", version="0.1.0")
sessions = SessionStore()
app.add_middleware(LocalSessionMiddleware, sessions=sessions)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1"],
)


@app.get("/api/session", response_model=LocalSession)
def get_session(request: Request) -> LocalSession:
    return sessions.issue(local_origin(request, required=False))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/devices", response_model=DeviceList)
def get_devices() -> DeviceList:
    return DeviceList(devices=discover_devices())

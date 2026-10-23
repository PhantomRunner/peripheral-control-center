"""Local-only read-only API. No firmware or settings operations."""

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .models import DeviceList
from .scanner import discover_devices

app = FastAPI(title="Peripheral Control Center API", version="0.1.0")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/devices", response_model=DeviceList)
def get_devices() -> DeviceList:
    return DeviceList(devices=discover_devices())

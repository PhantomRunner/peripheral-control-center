from typing import Literal

from pydantic import BaseModel, Field


class DeviceSummary(BaseModel):
    id: str
    name: str
    kind: Literal["mouse", "keyboard"]
    status: Literal["offline", "receiver_detected", "wired_detected"]
    connected_usb_ids: list[str] = Field(default_factory=list)
    battery_percent: int | None = None
    dpi: int | None = None
    polling_rate_hz: int | None = None
    driver_state: Literal["not_implemented"] = "not_implemented"
    note: str


class DeviceList(BaseModel):
    devices: list[DeviceSummary]

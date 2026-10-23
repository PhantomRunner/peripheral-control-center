from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DeviceCapabilities(BaseModel):
    """Operations implemented by this adapter, not promises about the hardware."""

    usb_discovery: bool = True
    battery_read: bool = False
    dpi_read: bool = False
    polling_rate_read: bool = False
    firmware_read: bool = False
    settings_write: bool = False


class DeviceConnection(BaseModel):
    """USB presence is independent of a validated wireless link."""

    source: Literal["usb_enumeration"] = "usb_enumeration"
    wired_usb_present: bool = False
    receiver_usb_present: bool = False
    wireless_link_verified: bool | None = None


class DeviceSummary(BaseModel):
    id: str
    name: str
    kind: Literal["mouse", "keyboard"]
    status: Literal["offline", "receiver_detected", "wired_detected"]
    connected_usb_ids: list[str] = Field(default_factory=list)
    battery_percent: int | None = None
    dpi: int | None = None
    polling_rate_hz: int | None = None
    firmware_version: str | None = None
    telemetry_updated_at: datetime | None = None
    settings_updated_at: datetime | None = None
    capabilities: DeviceCapabilities = Field(default_factory=DeviceCapabilities)
    connection: DeviceConnection = Field(default_factory=DeviceConnection)
    driver_state: Literal["not_implemented", "read_only"] = "not_implemented"
    note: str


class DeviceList(BaseModel):
    devices: list[DeviceSummary]

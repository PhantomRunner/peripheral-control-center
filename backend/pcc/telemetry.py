"""Manual PSSTX21 reads observed on 2026-10-23, with independent timestamps.

Enumeration only attaches the last timestamped observation. It never starts HID IO.
Standalone children retain descriptor/ownership checks and fixed output budgets.
"""

import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from .drivers import registry
from .config_telemetry import ConfigReadUnavailable, ConfigSnapshot, read_pulsar_config
from .keyboard_control import ControlSnapshot, ControlUnavailable, read_ajazz_control
from .models import DeviceSummary
from .settings import StrictModel


class TelemetryUnavailable(Exception):
    pass


class TelemetryBusy(Exception):
    pass


class TelemetryConsentRequired(Exception):
    pass


class ReadTelemetryRequest(StrictModel):
    vendor_tools_closed: bool


class _ObservedFields(StrictModel):
    battery_percent: int = Field(ge=0, le=100)
    charging: bool
    mouse_firmware_candidate: str | None = Field(pattern=r"^[0-9]+\.[0-9a-f]{2}$")


class _ProbeResult(StrictModel):
    status: Literal["candidate_read_replies_observed"]
    usb_id: Literal["3710:5406"]
    device_model_verified: Literal[False]
    adapter_enabled: Literal[False]
    observed: _ObservedFields
    ownership_basis: Literal["operator_closed_vendor_tools_and_visible_handles_checked"]


class TelemetrySnapshot(StrictModel):
    device_id: Literal["pulsar_susanto_x"] = "pulsar_susanto_x"
    battery_percent: int = Field(ge=0, le=100)
    charging: bool
    firmware_version: str | None = Field(pattern=r"^[0-9]+\.[0-9a-f]{2}$")
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def read_pulsar_snapshot() -> TelemetrySnapshot:
    """Run the fixed diagnostic once. Never retry after an uncertain result."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pcc.diagnostics.pulsar_probe", "--execute", "--vendor-tools-closed"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
            timeout=10, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 8192:
            raise TelemetryUnavailable("Battery/firmware read was not confirmed.")
        reading = _ProbeResult.model_validate_json(result.stdout).observed
        return TelemetrySnapshot(battery_percent=reading.battery_percent, charging=reading.charging, firmware_version=reading.mouse_firmware_candidate)
    except (OSError, subprocess.TimeoutExpired, ValidationError):
        raise TelemetryUnavailable("Battery/firmware read was not confirmed.") from None


class TelemetryService:
    def __init__(self, reader: Callable[[], TelemetrySnapshot] = read_pulsar_snapshot,
                 *, config_reader: Callable[[], ConfigSnapshot] = read_pulsar_config,
                 control_reader: Callable[[], ControlSnapshot] = read_ajazz_control) -> None:
        self._reader = reader
        self._config_reader = config_reader
        self._control_reader = control_reader
        self._control_snapshot: ControlSnapshot | None = None
        self._snapshot: TelemetrySnapshot | None = None
        self._config_snapshot: ConfigSnapshot | None = None
        self._config_generation = 0
        self._state_lock = threading.Lock()
        self._operation_lock = threading.Lock()

    def summaries(self) -> list[DeviceSummary]:
        devices = registry.discover_devices()
        with self._state_lock:
            for device in devices:
                if device.id == "ajazz_ak820_pro":
                    if not device.connection.wired_usb_present:
                        self._control_snapshot = None
                    elif self._control_snapshot is not None:
                        device.control_responded = True
                        device.control_checked_at = self._control_snapshot.recorded_at
                if device.id != "pulsar_susanto_x":
                    continue
                if device.status == "offline":
                    self._snapshot = None
                    self._config_snapshot = None
                    self._config_generation += 1
                else:
                    if self._snapshot is not None:
                        device.battery_percent = self._snapshot.battery_percent
                        device.firmware_version = self._snapshot.firmware_version
                        device.telemetry_updated_at = self._snapshot.recorded_at
                    if self._config_snapshot is not None:
                        device.dpi = self._config_snapshot.dpi
                        device.polling_rate_hz = self._config_snapshot.polling_rate_hz
                        device.settings_updated_at = self._config_snapshot.recorded_at
        return devices

    def read(self, *, vendor_tools_closed: bool) -> TelemetrySnapshot:
        if vendor_tools_closed is not True:
            raise TelemetryConsentRequired("Close other device-control tools before reading.")
        if not self._operation_lock.acquire(blocking=False):
            raise TelemetryBusy("A hardware read is already running.")
        try:
            devices = registry.discover_devices()
            if not any(device.id == "pulsar_susanto_x" and device.status == "receiver_detected" for device in devices):
                raise TelemetryUnavailable("Receiver is not detected.")
            snapshot = self._reader()
            with self._state_lock:
                self._snapshot = snapshot
            return snapshot
        except (TelemetryUnavailable, OSError):
            with self._state_lock:
                self._snapshot = None
            raise TelemetryUnavailable("Battery/firmware read was not confirmed.") from None
        finally:
            self._operation_lock.release()

    def read_config(self, *, vendor_tools_closed: bool) -> ConfigSnapshot:
        if vendor_tools_closed is not True:
            raise TelemetryConsentRequired("Close other device-control tools before reading.")
        if not self._operation_lock.acquire(blocking=False):
            raise TelemetryBusy("A hardware read is already running.")
        try:
            devices = registry.discover_devices()
            if not any(device.id == "pulsar_susanto_x" and device.status == "receiver_detected" for device in devices):
                raise ConfigReadUnavailable
            with self._state_lock:
                generation = self._config_generation
            snapshot = self._config_reader()
            with self._state_lock:
                if generation == self._config_generation:
                    self._config_snapshot = snapshot
            return snapshot
        except (ConfigReadUnavailable, OSError):
            with self._state_lock:
                self._config_snapshot = None
            raise TelemetryUnavailable("DPI/polling read was not confirmed.") from None
        finally:
            self._operation_lock.release()

    def invalidate_config(self) -> None:
        with self._state_lock:
            self._config_generation += 1
            self._config_snapshot = None

    def read_control(self, *, vendor_tools_closed: bool) -> ControlSnapshot:
        if vendor_tools_closed is not True:
            raise TelemetryConsentRequired("Close other device-control tools before reading.")
        if not self._operation_lock.acquire(blocking=False):
            raise TelemetryBusy("A hardware read is already running.")
        try:
            devices = registry.discover_devices()
            if not any(d.id == "ajazz_ak820_pro" and d.connection.wired_usb_present for d in devices):
                raise ControlUnavailable
            snapshot = self._control_reader()
            with self._state_lock:
                self._control_snapshot = snapshot
            return snapshot
        except (ControlUnavailable, OSError):
            with self._state_lock:
                self._control_snapshot = None
            raise TelemetryUnavailable("Wired control response was not confirmed.") from None
        finally:
            self._operation_lock.release()

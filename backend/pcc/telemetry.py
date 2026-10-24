"""Manual PSSTX21 reads observed on 2026-10-23, with independent timestamps.

Enumeration only attaches the last timestamped observation. It never starts HID IO.
Standalone children retain descriptor/ownership checks and fixed output budgets.
"""

import math
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
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


POLL_INTERVAL_SECONDS = 60


class TelemetryCooldown(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("Battery polling is limited to once per minute.")


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
                 control_reader: Callable[[], ControlSnapshot] = read_ajazz_control,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._reader = reader
        self._config_reader = config_reader
        self._control_reader = control_reader
        self._control_snapshot: ControlSnapshot | None = None
        self._snapshot: TelemetrySnapshot | None = None
        self._config_snapshot: ConfigSnapshot | None = None
        self._config_generation = 0
        self._connection_generation = {"pulsar_susanto_x": 0, "ajazz_ak820_pro": 0}
        self._presence: dict[str, bool] = {}
        self._state_lock = threading.Lock()
        self._operation_lock = threading.Lock()
        self._clock = clock
        self._battery_finished_at: float | None = None

    def summaries(self) -> list[DeviceSummary]:
        with self._state_lock:
            devices = registry.discover_devices()
            present = {device.id: (device.connection.wired_usb_present if device.id == "ajazz_ak820_pro"
                                   else device.status == "receiver_detected") for device in devices}
            for device_id in self._connection_generation:
                attached = present.get(device_id, False)
                if self._presence.get(device_id) != attached:
                    self._connection_generation[device_id] += 1
                self._presence[device_id] = attached
                if not attached:
                    if device_id == "ajazz_ak820_pro":
                        self._control_snapshot = None
                    else:
                        self._snapshot = None
                        self._config_snapshot = None
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

    def _connection(self, device_id: str) -> int:
        self.summaries()  # Observe USB removal even when no dashboard request is running.
        with self._state_lock:
            if not self._presence.get(device_id):
                raise TelemetryUnavailable("USB control hardware is not detected.")
            return self._connection_generation[device_id]

    def _same_connection(self, device_id: str, generation: int) -> None:
        # Called under the state lock after a final passive scan.
        if not self._presence.get(device_id) or self._connection_generation[device_id] != generation:
            raise TelemetryUnavailable("USB connection changed during the read.")

    def read(self, *, vendor_tools_closed: bool, polling: bool = False) -> TelemetrySnapshot:
        if vendor_tools_closed is not True:
            raise TelemetryConsentRequired("Close other device-control tools before reading.")
        if not self._operation_lock.acquire(blocking=False):
            raise TelemetryBusy("A hardware read is already running.")
        attempted = False
        try:
            if polling and self._battery_finished_at is not None:
                remaining = POLL_INTERVAL_SECONDS - (self._clock() - self._battery_finished_at)
                if remaining > 0:
                    raise TelemetryCooldown(math.ceil(remaining))
            connection = self._connection("pulsar_susanto_x")
            attempted = True
            snapshot = self._reader()
            self.summaries()
            with self._state_lock:
                self._same_connection("pulsar_susanto_x", connection)
                self._snapshot = snapshot
            return snapshot
        except (TelemetryUnavailable, OSError):
            with self._state_lock:
                self._snapshot = None
            raise TelemetryUnavailable("Battery/firmware read was not confirmed.") from None
        finally:
            if attempted:
                self._battery_finished_at = self._clock()
            self._operation_lock.release()

    def read_config(self, *, vendor_tools_closed: bool) -> ConfigSnapshot:
        if vendor_tools_closed is not True:
            raise TelemetryConsentRequired("Close other device-control tools before reading.")
        if not self._operation_lock.acquire(blocking=False):
            raise TelemetryBusy("A hardware read is already running.")
        try:
            connection = self._connection("pulsar_susanto_x")
            with self._state_lock:
                generation = self._config_generation
            snapshot = self._config_reader()
            self.summaries()
            with self._state_lock:
                self._same_connection("pulsar_susanto_x", connection)
                if generation == self._config_generation:
                    self._config_snapshot = snapshot
            return snapshot
        except (ConfigReadUnavailable, TelemetryUnavailable, OSError):
            with self._state_lock:
                self._config_snapshot = None
            raise TelemetryUnavailable("DPI/polling read was not confirmed.") from None
        finally:
            self._operation_lock.release()

    def invalidate_config(self) -> None:
        with self._state_lock:
            self._config_generation += 1
            self._config_snapshot = None

    @contextmanager
    def pulsar_operation(self):
        """Serialize new performance operations with reads and reject stale completion."""
        if not self._operation_lock.acquire(blocking=False):
            raise TelemetryBusy('A hardware operation is already running.')
        try:
            connection = self._connection('pulsar_susanto_x')
            with self._state_lock:
                config_generation = self._config_generation
            yield
            self.summaries()
            with self._state_lock:
                self._same_connection('pulsar_susanto_x', connection)
                if config_generation != self._config_generation:
                    raise TelemetryUnavailable('Settings changed during the operation.')
        finally:
            self._operation_lock.release()

    def read_control(self, *, vendor_tools_closed: bool) -> ControlSnapshot:
        if vendor_tools_closed is not True:
            raise TelemetryConsentRequired("Close other device-control tools before reading.")
        if not self._operation_lock.acquire(blocking=False):
            raise TelemetryBusy("A hardware read is already running.")
        try:
            connection = self._connection("ajazz_ak820_pro")
            snapshot = self._control_reader()
            self.summaries()
            with self._state_lock:
                self._same_connection("ajazz_ak820_pro", connection)
                self._control_snapshot = snapshot
            return snapshot
        except (ControlUnavailable, TelemetryUnavailable, OSError):
            with self._state_lock:
                self._control_snapshot = None
            raise TelemetryUnavailable("Wired control response was not confirmed.") from None
        finally:
            self._operation_lock.release()

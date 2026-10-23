"""Wired static RGB with command acknowledgement, not fabricated readback."""

import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from pcc.apply_settings import RgbAcknowledgement
from pcc.settings import KeyboardSettings, RgbSettings, StrictModel
from .registry import discover_devices
from .protocols.ajazz_rgb import static_rgb_payload


class _Requested(StrictModel):
    mode: Literal["static"]
    color: str = Field(pattern=r"^#[0-9a-f]{6}$")
    brightness_level: int = Field(ge=0, le=5)


class _Diagnostics(StrictModel):
    phase: Literal["save"]
    feature_sets_attempted: Literal[4]
    feature_sets_completed: Literal[4]
    feature_gets_attempted: Literal[4]
    last_received_length: Literal[64, 65]
    last_known_ack_command: Literal[2]
    last_known_ack_success: Literal[True]


class _Result(StrictModel):
    status: Literal["lighting_sequence_acknowledged"]
    usb_id: Literal["0c45:8009"]
    requested: _Requested
    acknowledged_commands: tuple[Literal[24], Literal[19], Literal[2]]
    actual_rgb: None
    battery_percent: None
    firmware_version: None
    persistence_verified: Literal[False]
    device_model_verified: Literal[False]
    adapter_enabled: Literal[False]
    diagnostics: _Diagnostics


class AjazzRgbAdapter:
    validation_reference = "Owner AK820 Pro 2026-10-23: exact FF13 sequence acknowledged; blue color visually confirmed"
    session_owns_device_lock = True  # The bounded child owns the lock through final ACK.

    @staticmethod
    def wired_usb_present() -> bool:
        return any(d.id == "ajazz_ak820_pro" and d.connection.wired_usb_present for d in discover_devices())

    @staticmethod
    def validate_rgb(desired: RgbSettings) -> None:
        static_rgb_payload(desired.color, desired.brightness_percent)

    def apply_rgb(self, desired: KeyboardSettings) -> RgbAcknowledgement:
        self.validate_rgb(desired.rgb)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pcc.diagnostics.ajazz_rgb_probe", "--apply-rgb",
                 "--color", desired.rgb.color, "--brightness-percent", str(desired.rgb.brightness_percent),
                 "--vendor-tools-closed", "--allow-device-memory-writes"],
                cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=10, check=False,
            )
            if result.returncode != 0 or len(result.stdout) > 8192:
                raise RuntimeError("RGB acknowledgement was not confirmed.")
            feedback = _Result.model_validate_json(result.stdout)
            if (feedback.requested.color != desired.rgb.color
                    or feedback.requested.brightness_level != desired.rgb.brightness_percent // 20):
                raise RuntimeError("RGB acknowledgement did not match the request.")
            return RgbAcknowledgement(requested=desired)
        except (OSError, subprocess.TimeoutExpired, ValidationError):
            raise RuntimeError("RGB acknowledgement was not confirmed; settings may have changed.") from None

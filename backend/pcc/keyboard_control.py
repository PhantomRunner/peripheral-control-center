"""Manual wired control-response check, without telemetry inference or SETs."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from .settings import StrictModel


class ControlUnavailable(Exception):
    pass


class ControlSnapshot(StrictModel):
    device_id: Literal["ajazz_ak820_pro"] = "ajazz_ak820_pro"
    responded: Literal[True] = True
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class _Diagnostics(StrictModel):
    phase: Literal["initial_feature"]
    feature_sets_attempted: Literal[0]
    feature_sets_completed: Literal[0]
    feature_gets_attempted: Literal[1]
    last_received_length: Literal[64, 65]
    last_known_ack_command: Literal[2, 19, 24] | None
    last_known_ack_success: bool | None


class _Result(StrictModel):
    status: Literal["control_report_received"]
    usb_id: Literal["0c45:8009"]
    actual_rgb: None
    battery_percent: None
    firmware_version: None
    device_model_verified: Literal[False]
    adapter_enabled: Literal[False]
    diagnostics: _Diagnostics


def read_ajazz_control() -> ControlSnapshot:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pcc.diagnostics.ajazz_rgb_probe", "--read-control", "--vendor-tools-closed"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 8192:
            raise ControlUnavailable
        _Result.model_validate_json(result.stdout)
        return ControlSnapshot()
    except (OSError, subprocess.TimeoutExpired, ValidationError):
        raise ControlUnavailable from None

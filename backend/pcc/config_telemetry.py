"""Manual current-profile DPI/polling reads verified on PSSTX21 on 2026-10-23."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from .drivers.protocols.pulsar_readonly import Reply, dpi_value, polling_rate
from .settings import StrictModel


class ConfigReadUnavailable(Exception):
    pass


class ConfigSnapshot(StrictModel):
    device_id: Literal["pulsar_susanto_x"] = "pulsar_susanto_x"
    dpi: int = Field(ge=1, le=32000)
    polling_rate_hz: Literal[125, 250, 500, 1000, 2000, 4000, 8000]
    active_profile_index: int = Field(ge=0, le=3)
    active_stage_index: int = Field(ge=0, le=5)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class _Identity(StrictModel):
    cid: Literal[87]
    mid: Literal[39]
    type: Literal[5]


class _Observed(StrictModel):
    dpi_candidate: int = Field(ge=1, le=32000)
    stored_polling_rate_hz_candidate: Literal[125, 250, 500, 1000, 2000, 4000, 8000]


class _Records(StrictModel):
    polling_hex: str = Field(pattern=r"^[0-9a-f]{2} [0-9a-f]{2}$")
    active_dpi_hex: str = Field(pattern=r"^[0-9a-f]{2}( [0-9a-f]{2}){3}$")


class _ConfigResult(StrictModel):
    status: Literal["candidate_current_settings_observed"]
    usb_id: Literal["3710:5406"]
    identity: _Identity
    active_profile_index: int = Field(ge=0, le=3)
    stage_count: int = Field(ge=1, le=6)
    active_stage_index: int = Field(ge=0, le=5)
    observed: _Observed
    setting_records: _Records
    adapter_enabled: Literal[False]
    settings_writes: Literal[0]
    output_reports_sent: Literal[12]
    ownership_basis: Literal["operator_closed_vendor_tools_and_visible_handles_checked"]


def read_pulsar_config() -> ConfigSnapshot:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pcc.diagnostics.pulsar_config_probe", "--execute", "--vendor-tools-closed"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
            timeout=10, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 8192:
            raise ConfigReadUnavailable
        reading = _ConfigResult.model_validate_json(result.stdout)
        dpi = dpi_value(Reply(8, bytes.fromhex(reading.setting_records.active_dpi_hex)))
        hz = polling_rate(Reply(8, bytes.fromhex(reading.setting_records.polling_hex)))
        if (reading.active_stage_index >= reading.stage_count
                or dpi != reading.observed.dpi_candidate
                or hz != reading.observed.stored_polling_rate_hz_candidate):
            raise ConfigReadUnavailable
        return ConfigSnapshot(dpi=dpi, polling_rate_hz=hz, active_profile_index=reading.active_profile_index,
                              active_stage_index=reading.active_stage_index)
    except (OSError, ValueError, subprocess.TimeoutExpired, ValidationError):
        raise ConfigReadUnavailable from None

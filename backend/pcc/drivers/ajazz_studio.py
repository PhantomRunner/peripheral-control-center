"""Bounded ACK-only writes validated on the owner's exact FF13 interface."""
import subprocess
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from pcc.settings import StrictModel
from pcc.studio_models import StudioIntent, requested_fields


class _Diagnostics(StrictModel):
    phase: Literal['save']
    feature_sets_attempted: Literal[4]
    feature_sets_completed: Literal[4]
    feature_gets_attempted: Literal[4]
    last_received_length: Literal[64,65]
    last_known_ack_command: Literal[2]
    last_known_ack_success: Literal[True]


class _Result(StrictModel):
    status: Literal['sequence_acknowledged_visual_check_required']
    operation: Literal['lighting','clock','standby']
    requested: dict
    usb_id: Literal['0c45:8009']
    actual_settings: None
    persistence_verified: Literal[False]
    diagnostics: _Diagnostics


class AjazzStudioAdapter:
    validation_reference = 'Owner 2026-10-24: exact FF13 lighting/clock/standby ACKs; blue Breathe visually confirmed'

    def apply(self, intent: StudioIntent) -> None:
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pcc.diagnostics.ajazz_studio_probe', '--operation', intent.operation,
                 '--apply', '--vendor-tools-closed', '--allow-device-memory-writes'],
                input=intent.model_dump_json(), cwd=Path(__file__).resolve().parents[2],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if result.returncode != 0 or len(result.stdout) > 8192:
                raise RuntimeError('Studio acknowledgement was not confirmed.')
            observed = _Result.model_validate_json(result.stdout)
            if observed.operation != intent.operation or json.dumps(observed.requested, sort_keys=True) != json.dumps(requested_fields(intent), sort_keys=True):
                raise RuntimeError('Studio acknowledgement did not match intent.')
        except (OSError, subprocess.TimeoutExpired, ValidationError):
            raise RuntimeError('Studio acknowledgement was not confirmed; settings may have changed.') from None

"""Fixed performance subprocess boundary, gated by exact-device evidence."""

import subprocess
import sys
from pathlib import Path
from typing import Literal

from pcc.performance_models import PerformanceSnapshot
from pcc.settings import StrictModel


class PerformanceUnavailable(Exception):
    pass


class _ReadResult(StrictModel):
    status: Literal['performance_observed']
    snapshot: PerformanceSnapshot
    output_reports_sent: int
    settings_write_reports: Literal[0]
    adapter_activation: Literal[False]


def read_performance() -> PerformanceSnapshot:
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pcc.diagnostics.pulsar_performance_probe', '--execute', '--vendor-tools-closed'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=26, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 16384:
            raise PerformanceUnavailable
        parsed = _ReadResult.model_validate_json(result.stdout)
        if parsed.output_reports_sent != 28 + 2 * parsed.snapshot.stage_count or parsed.snapshot.firmware_version != '3.03':
            raise PerformanceUnavailable
        return parsed.snapshot
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise PerformanceUnavailable('Performance read was not confirmed.') from None

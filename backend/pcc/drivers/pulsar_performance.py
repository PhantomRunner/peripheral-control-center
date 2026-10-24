"""Fixed performance subprocess boundary, gated by exact-device evidence."""

import subprocess
import sys
from pathlib import Path
from typing import Literal

from pcc.performance_models import PerformanceApplyRequest, PerformanceApplyResult, PerformanceSnapshot, validate_apply_context
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


class _ApplyResult(StrictModel):
    result: PerformanceApplyResult
    output_reports_sent: int
    settings_write_reports: int


def apply_performance(request: PerformanceApplyRequest) -> PerformanceSnapshot:
    try:
        result = subprocess.run(
            [sys.executable,'-m','pcc.diagnostics.pulsar_performance_apply','--apply'],
            input=request.model_dump_json(),cwd=Path(__file__).resolve().parents[1],
            capture_output=True,text=True,timeout=52,check=False,
        )
        if result.returncode != 0 or len(result.stdout)>16384:
            raise PerformanceUnavailable
        parsed = _ApplyResult.model_validate_json(result.stdout)
        writes = parsed.settings_write_reports
        actual = parsed.result.actual
        if (parsed.result.requested != request.action or writes not in ({1,2} if request.action.operation=='rotation' else {1})
                or parsed.output_reports_sent != 56 + 4*actual.stage_count + writes or actual.firmware_version != '3.03'):
            raise PerformanceUnavailable
        validate_apply_context(request,actual)
        return actual
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise PerformanceUnavailable('Performance Apply was not confirmed; state may have changed.') from None

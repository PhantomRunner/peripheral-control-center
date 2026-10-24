"""One semantic change with consistent before/after records; no retry/rollback."""

from pcc.diagnostics.pulsar_performance_probe import observe_details
from pcc.drivers.protocols.pulsar_performance import Register, pair, write_record
from pcc.performance_models import PerformanceApplyRequest, PerformanceCapabilities, PerformanceSnapshot
from pcc.performance_support import validate_action


def apply_one(transport, request: PerformanceApplyRequest, capabilities: PerformanceCapabilities) -> PerformanceSnapshot:
    validate_action(request.action, capabilities)
    if not request.vendor_tools_closed or not request.allow_device_memory_writes:
        raise ValueError('Explicit tool and memory consent required.')
    before, context, records = observe_details(transport)
    if (before.active_profile_index != request.expected_profile_index
            or before.active_stage_index != request.expected_active_stage_index):
        raise ValueError('The expected profile or stage changed before Apply.')
    action = request.action
    if action.operation in {'stage_dpi','active_stage'} and action.stage_index >= before.stage_count:
        raise ValueError('The selected stage does not exist.')
    if action.operation == 'stage_dpi' and any(v is None for v in (before.stages[action.stage_index].x,before.stages[action.stage_index].y)):
        raise ValueError('Unknown DPI encoding is not writable.')
    if action.operation in {'lod','debounce','motion_sync','angle_snap','ripple_control','turbo','rotation'} and getattr(before.sensor,action.operation) is None:
        raise ValueError('Sensor support was not confirmed.')
    register, record = write_record(action)
    expected_records = {**records}
    if register in records:
        expected_records[register] = record
    if action.operation == 'rotation':
        if before.sensor.rotation_enabled is None:
            raise ValueError('Rotation enable state is unavailable.')
        expected_records[Register.ROTATION_STATE] = pair(1)
    expected_context = {**context}
    if action.operation == 'active_stage':
        expected_context['active'] = action.stage_index
    # The transport accepts this typed action once. Rotation may require its
    # finite enable+angle pair, still one selected semantic change.
    transport.write_action(action, rotation_enabled=before.sensor.rotation_enabled)
    after, final_context, final_records = observe_details(transport)
    if final_context != expected_context or final_records != expected_records:
        raise ValueError('Readback failed or an unrequested setting changed; state may have changed.')
    return after

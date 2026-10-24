"""Exact-PSSTX21 evidence gates. Never enable by environment or client flags."""

from .performance_models import PerformanceAction, PerformanceCapabilities


def validated_capabilities() -> PerformanceCapabilities:
    # Read and write experiments are pending. Codec/fake-test success is not
    # device validation. Enable each parameter only with recorded exact evidence.
    return PerformanceCapabilities()


def validate_action(action: PerformanceAction, capabilities: PerformanceCapabilities) -> None:
    cap = capabilities.parameters.get(action.operation)
    if cap is None or not capabilities.snapshot_read or not cap.read or not cap.write:
        raise ValueError('This performance write is not validated.')
    values = action.model_dump(exclude={'operation', 'stage_index'})
    value = action.stage_index if action.operation == 'active_stage' else next(iter(values.values()))
    if cap.values:
        if not any(type(value) is type(v) and value == v for v in cap.values):
            raise ValueError('Value is outside the validated set.')
    elif (type(value) is not int or cap.minimum is None or cap.maximum is None
          or not cap.minimum <= value <= cap.maximum or (cap.step is not None and (value - cap.minimum) % cap.step)):
        raise ValueError('Value is outside the validated range.')

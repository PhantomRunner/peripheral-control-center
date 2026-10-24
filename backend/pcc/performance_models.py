"""Semantic Pulsar performance contracts, independent of HID framing."""

from datetime import datetime, timezone
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .settings import StrictModel

Parameter = Literal['stage_dpi', 'active_stage', 'polling_rate', 'lod', 'debounce',
                    'motion_sync', 'angle_snap', 'ripple_control', 'turbo', 'rotation']
SensorParameter = Literal['lod', 'debounce', 'motion_sync', 'angle_snap', 'ripple_control', 'turbo', 'rotation']
PARAMETERS = Parameter.__args__


class ParameterCapability(StrictModel):
    read: bool = False
    write: bool = False
    values: list[int | float | bool] = Field(default_factory=list, max_length=32)
    minimum: int | None = None
    maximum: int | None = None
    step: int | None = None


class PerformanceCapabilities(StrictModel):
    snapshot_read: bool = False
    parameters: dict[Parameter, ParameterCapability] = Field(default_factory=lambda: {
        name: ParameterCapability() for name in PARAMETERS
    })


class DpiStage(StrictModel):
    index: int = Field(ge=0, le=5)
    x: int | None = Field(default=None, ge=10, le=32000)
    y: int | None = Field(default=None, ge=10, le=32000)


class SensorSnapshot(StrictModel):
    lod: float | None = None
    debounce: int | None = Field(default=None, ge=0, le=15)
    motion_sync: bool | None = None
    angle_snap: bool | None = None
    ripple_control: bool | None = None
    turbo: bool | None = None
    rotation: int | None = Field(default=None, ge=-30, le=30)


class PerformanceSnapshot(StrictModel):
    device_id: Literal['pulsar_susanto_x'] = 'pulsar_susanto_x'
    firmware_version: str = Field(pattern=r'^[0-9]+\.[0-9a-f]{2}$')
    active_profile_index: int = Field(ge=0, le=3)
    stage_count: int = Field(ge=1, le=6)
    active_stage_index: int = Field(ge=0, le=5)
    stages: list[DpiStage] = Field(min_length=1, max_length=6)
    polling_rate_hz: int | None = None
    sensor: SensorSnapshot
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode='after')
    def consistent_stages(self) -> Self:
        if self.active_stage_index >= self.stage_count or [s.index for s in self.stages] != list(range(self.stage_count)):
            raise ValueError('Inconsistent DPI stages.')
        if self.polling_rate_hz is not None and self.polling_rate_hz not in {125, 250, 500, 1000, 2000, 4000, 8000}:
            raise ValueError('Unknown polling rate.')
        if self.sensor.lod is not None and self.sensor.lod not in {0.7, 1.0, 2.0}:
            raise ValueError('Unknown lift-off distance.')
        return self


class StageDpiAction(StrictModel):
    operation: Literal['stage_dpi']
    stage_index: int = Field(ge=0, le=5)
    dpi: int = Field(ge=10, le=32000)


class ActiveStageAction(StrictModel):
    operation: Literal['active_stage']
    stage_index: int = Field(ge=0, le=5)


class PollingAction(StrictModel):
    operation: Literal['polling_rate']
    hz: int = Field(ge=125, le=8000)

    @model_validator(mode='after')
    def known_rate(self) -> Self:
        if self.hz not in {125, 250, 500, 1000, 2000, 4000, 8000}:
            raise ValueError('Unknown polling rate.')
        return self


class LodAction(StrictModel):
    operation: Literal['lod']
    millimetres: float

    @model_validator(mode='after')
    def known_lod(self) -> Self:
        if self.millimetres not in {0.7, 1.0, 2.0}:
            raise ValueError('Unknown lift-off distance.')
        return self


class DebounceAction(StrictModel):
    operation: Literal['debounce']
    milliseconds: int = Field(ge=0, le=15)


class SwitchAction(StrictModel):
    operation: Literal['motion_sync', 'angle_snap', 'ripple_control', 'turbo']
    enabled: bool


class RotationAction(StrictModel):
    operation: Literal['rotation']
    degrees: int = Field(ge=-30, le=30)


PerformanceAction = Annotated[StageDpiAction | ActiveStageAction | PollingAction | LodAction |
                              DebounceAction | SwitchAction | RotationAction, Field(discriminator='operation')]


class PerformanceReadRequest(StrictModel):
    vendor_tools_closed: bool = False


class PerformanceApplyRequest(PerformanceReadRequest):
    allow_device_memory_writes: bool = False
    action: PerformanceAction
    expected_profile_index: int = Field(ge=0, le=3)
    expected_active_stage_index: int = Field(ge=0, le=5)


class PerformanceApplyResult(StrictModel):
    status: Literal['verified'] = 'verified'
    requested: PerformanceAction
    actual: PerformanceSnapshot
    persistence_verified: Literal[False] = False
    may_persist: Literal[True] = True

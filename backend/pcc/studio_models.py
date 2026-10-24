"""Strict semantic Studio requests; no client protocol/packet parameters."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pcc.settings import StrictModel
from pcc.drivers.protocols.ajazz_studio import StudioLighting


class LightingIntent(StrictModel):
    operation: Literal['lighting']
    settings: StudioLighting


class ClockIntent(StrictModel):
    operation: Literal['clock']
    local_time: str = Field(min_length=20, max_length=40)

    @field_validator('local_time')
    @classmethod
    def aware_clock(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None or not 2000 <= parsed.year <= 2099:
            raise ValueError('An explicit timezone and year 2000–2099 are required.')
        return parsed.isoformat()


class StandbyIntent(StrictModel):
    operation: Literal['standby']
    minutes: Literal[0, 1, 5, 30]

    @field_validator('minutes', mode='before')
    @classmethod
    def strict_minutes(cls, value):
        if type(value) is not int:
            raise ValueError('Standby minutes must be an integer.')
        return value


StudioIntent = Annotated[LightingIntent | ClockIntent | StandbyIntent, Field(discriminator='operation')]


class StudioApplyRequest(StrictModel):
    intent: StudioIntent
    vendor_tools_closed: bool = False
    allow_device_memory_writes: bool = False


class StudioApplyResult(StrictModel):
    status: Literal['acknowledged'] = 'acknowledged'
    device_id: Literal['ajazz_ak820_pro'] = 'ajazz_ak820_pro'
    requested: StudioIntent
    actual_settings: None = None
    persistence_verified: Literal[False] = False


def requested_fields(intent: StudioIntent) -> dict:
    if isinstance(intent, LightingIntent): return intent.settings.model_dump()
    if isinstance(intent, ClockIntent): return {'local_time': intent.local_time}
    return {'minutes': intent.minutes}

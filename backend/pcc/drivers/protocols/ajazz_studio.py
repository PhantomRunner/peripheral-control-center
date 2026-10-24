"""Source-derived bounded Studio plans; not proof of exact-device support.

Reference: kabelklaus/ajazz-ak820-pro at 4b69f3cb57506f518e5b2f9f5f56e07e8b9411d6.
MIT, Copyright (c) 2026 kabelklaus. Full notice: LICENSE.ajazz-ak820-pro.
No device IO occurs in this module. No raw command/packet input is accepted.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field, field_validator

from pcc.settings import StrictModel
from .ajazz_rgb import BRIGHTNESS_STEPS

Effect = Literal['off', 'static', 'key_on', 'key_off', 'glitter', 'falling', 'colourful', 'breathe',
                 'spectrum', 'outward', 'scroll', 'roll', 'rotate', 'explode', 'launch', 'ripple', 'flow', 'pulse', 'tilt', 'shuttle']
EFFECT_IDS = {name: index for index, name in enumerate(Effect.__args__)}
DIRECTION_IDS = {'left': 0, 'down': 1, 'up': 2, 'right': 3}


class StudioLighting(StrictModel):
    effect: Effect
    color: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    brightness: int = Field(ge=0, le=100)
    speed: int = Field(ge=0, le=5)
    direction: Literal['left', 'down', 'up', 'right']
    rainbow: bool

    @field_validator('color')
    @classmethod
    def color_case(cls, value: str) -> str:
        return value.lower()

    @field_validator('brightness')
    @classmethod
    def brightness_step(cls, value: int) -> int:
        if value not in BRIGHTNESS_STEPS:
            raise ValueError('Unsupported brightness level.')
        return value


class Command(Enum):
    START = (0x18, 0)
    LIGHTING = (0x13, 0)
    CLOCK = (0x28, 0)
    STANDBY = (0x17, 1)
    IMAGE = (0x72, 3)
    SAVE = (2, 0)


def command_payload(command: Command) -> bytes:
    if type(command) is not Command:
        raise ValueError('Only named Studio commands are supported.')
    payload = bytearray(64)
    payload[:3] = bytes((4, *command.value))
    payload[8] = 0 if command is Command.SAVE else 1
    return bytes(payload)


def lighting_payload(settings: StudioLighting) -> bytes:
    payload = bytearray(64)
    payload[0] = EFFECT_IDS[settings.effect]
    payload[1:4] = bytes.fromhex(settings.color[1:])
    payload[8:12] = bytes((int(settings.rainbow), settings.brightness // 20, settings.speed, DIRECTION_IDS[settings.direction]))
    payload[14:16] = bytes((0x55, 0xAA))
    return bytes(payload)


def clock_payload(value: datetime) -> bytes:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None or not 2000 <= value.year <= 2099:
        raise ValueError('Clock requires a timezone-aware date between 2000 and 2099.')
    payload = bytearray(64)
    payload[:11] = bytes((0, 1, 0x5A, value.year - 2000, value.month, value.day, value.hour, value.minute, value.second, 0, 4))
    payload[62:64] = bytes((0xAA, 0x55))
    return bytes(payload)


def standby_payload(minutes: int) -> bytes:
    if type(minutes) is not int or minutes not in (0, 1, 5, 30):
        raise ValueError('Standby supports only never, 1, 5 and 30 minutes.')
    payload = bytearray(64)
    payload[8] = (0, 1, 5, 30).index(minutes)
    payload[62:64] = bytes((0xAA, 0x55))
    return bytes(payload)


@dataclass(frozen=True)
class FeatureStep:
    name: str
    payload: bytes
    acknowledgement: Command | None


@dataclass(frozen=True)
class ControlPlan:
    operation: str
    requested: dict
    steps: tuple[FeatureStep, ...]


def control_plan(operation: Literal['lighting', 'clock', 'standby'], desired: StudioLighting | datetime | int) -> ControlPlan:
    if operation == 'lighting' and isinstance(desired, StudioLighting):
        config, data, requested = Command.LIGHTING, lighting_payload(desired), desired.model_dump()
    elif operation == 'clock' and isinstance(desired, datetime):
        config, data, requested = Command.CLOCK, clock_payload(desired), {'local_time': desired.isoformat()}
    elif operation == 'standby' and type(desired) is int:
        config, data, requested = Command.STANDBY, standby_payload(desired), {'minutes': desired}
    else:
        raise ValueError('The desired value does not match a supported operation.')
    return ControlPlan(operation, requested, (
        FeatureStep('start', command_payload(Command.START), Command.START),
        FeatureStep('configure', command_payload(config), config),
        FeatureStep('data', data, None),
        FeatureStep('save', command_payload(Command.SAVE), Command.SAVE),
    ))


def parse_ack(payload: bytes, expected: Command) -> None:
    if type(expected) is not Command or len(payload) != 64 or payload[:4] != bytes((4, *expected.value, 1)):
        raise ValueError('No matching complete Studio command acknowledgement.')


def screen_test_payload() -> bytes:
    """One fixed static blue/white checkerboard; no arbitrary image input."""
    payload = bytearray(b'\xff' * (9 * 4096))
    payload[:2] = bytes((1, 0))
    for y in range(128):
        for x in range(128):
            word = 0xFFFF if ((x // 16) + (y // 16)) % 2 else 0x441F
            offset = 256 + (y * 128 + x) * 2
            payload[offset:offset + 2] = word.to_bytes(2, 'little')
    return bytes(payload)


def screen_config_payload() -> bytes:
    payload = bytearray(64)
    payload[:3] = bytes((4, 0x72, 3))  # Only the source's AKS075 variant; no fallback.
    payload[8:10] = (9).to_bytes(2, 'little')
    return bytes(payload)

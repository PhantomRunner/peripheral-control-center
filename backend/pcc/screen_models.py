"""Bounded RGB565 artwork, not caller-controlled HID reports or framing."""
import base64
import hashlib
from pydantic import Field, field_validator, model_validator
from pcc.settings import StrictModel

FRAME_BYTES = 32768
MAX_FRAMES = 120
MAX_REQUEST_BYTES = 5_400_000


class ScreenFrame(StrictModel):
    rgb565_base64: str = Field(min_length=43692, max_length=43692)
    delay_ms: int = Field(ge=0, le=655350)

    @field_validator('rgb565_base64')
    @classmethod
    def complete_frame(cls, value: str) -> str:
        try: decoded = base64.b64decode(value, validate=True)
        except ValueError: raise ValueError('Invalid screen pixel encoding.') from None
        if len(decoded) != FRAME_BYTES: raise ValueError('Screen frames must contain 128×128 RGB565 pixels.')
        return value


class ScreenIntent(StrictModel):
    frames: list[ScreenFrame] = Field(min_length=1, max_length=MAX_FRAMES)

    @model_validator(mode='after')
    def bounded_animation(self):
        if len(self.frames) > 1 and any(frame.delay_ms < 20 for frame in self.frames):
            raise ValueError('Animation frame delays must be at least 20 ms.')
        return self


class ScreenApplyRequest(ScreenIntent):
    vendor_tools_closed: bool = False
    allow_device_memory_writes: bool = False


def artwork_payload(intent: ScreenIntent) -> bytes:
    count = len(intent.frames)
    output = bytearray(b'\xff' * (((256 + count * FRAME_BYTES + 4095) // 4096) * 4096))
    output[0] = count
    for index, frame in enumerate(intent.frames):
        output[index + 1] = 0 if count == 1 else max(1, min(255, (frame.delay_ms + 1) // 2))
        start = 256 + index * FRAME_BYTES
        output[start:start + FRAME_BYTES] = base64.b64decode(frame.rgb565_base64, validate=True)
    return bytes(output)


def artwork_digest(intent: ScreenIntent) -> str:
    return hashlib.sha256(artwork_payload(intent)).hexdigest()

"""Static FF13 RGB data; same framing as the owner's confirmed blue experiment.

Reference: kabelklaus/ajazz-ak820-pro at 4b69f3cb57506f518e5b2f9f5f56e07e8b9411d6.
MIT, Copyright (c) 2026 kabelklaus. See LICENSE.ajazz-ak820-pro.
ACK feedback does not establish current RGB or reconnect persistence.
"""

import re

BRIGHTNESS_STEPS = (0, 20, 40, 60, 80, 100)


def static_rgb_payload(color: str, brightness_percent: int) -> bytes:
    if (type(color) is not str or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None
            or type(brightness_percent) is not int or brightness_percent not in BRIGHTNESS_STEPS):
        raise ValueError("Static RGB requires a hex color and a supported brightness step.")
    payload = bytearray(64)
    payload[0] = 1
    payload[1:4] = bytes.fromhex(color[1:])
    payload[9] = brightness_percent // 20
    payload[14:16] = bytes((0x55, 0xAA))
    return bytes(payload)

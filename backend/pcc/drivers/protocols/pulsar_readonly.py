"""Candidate Nordic-family reply parsing; NOT validated PSSTX21 live support.

No command builder, output transport, profile switch or device open exists here.
Protocol/encoding reference: packerlschupfer/pulsar-mouse-linux at
297dbf4bb933545e5a2e6f393f2c81d64bc7c347 (MIT).
Copyright (c) 2026 Packerlschupfer. See LICENSE.pulsar-mouse-linux.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

READ_COMMANDS = frozenset({0x01, 0x03, 0x04, 0x08, 0x0E, 0x12, 0x1D})
POLLING_CODES = {0x01: 1000, 0x02: 500, 0x04: 250, 0x08: 125, 0x10: 2000, 0x20: 4000, 0x40: 8000}


class InvalidReply(ValueError):
    pass


class ReplyTimeout(TimeoutError):
    pass


@dataclass(frozen=True)
class ExpectedReply:
    command: int
    address: int | None = None
    length: int | None = None

    def __post_init__(self) -> None:
        if self.command not in READ_COMMANDS:
            raise ValueError("Only candidate read replies are supported.")
        if self.command == 0x08:
            if self.address is None or not 0 <= self.address <= 0xFFFF or self.length is None or not 1 <= self.length <= 10:
                raise ValueError("A bounded memory reply requires address and length.")
        elif self.address is not None or self.length is not None:
            raise ValueError("Only memory replies carry an expected address and length.")


@dataclass(frozen=True)
class Reply:
    command: int
    payload: bytes


def parse_reply(packet: bytes, expected: ExpectedReply) -> Reply:
    if len(packet) != 17 or packet[0] != 0x08 or sum(packet) & 0xFF != 0x55:
        raise InvalidReply("Invalid configuration report framing.")
    if packet[1] != expected.command or packet[2] != 0:
        raise InvalidReply("Reply does not match the successful query.")
    length = packet[5]
    if not 0 <= length <= 10:
        raise InvalidReply("Invalid reply payload length.")
    if expected.command == 0x08 and (int.from_bytes(packet[3:5], "big") != expected.address or length != expected.length):
        raise InvalidReply("Memory reply does not match the requested range.")
    return Reply(command=expected.command, payload=packet[6:6 + length])


class ReportSource(Protocol):
    def read_report(self, timeout_seconds: float) -> bytes:
        """Return an input report or raise TimeoutError; never send a query."""
        ...


def receive_reply(
    source: ReportSource, expected: ExpectedReply, *, timeout_seconds: float = 1.0,
    max_reports: int = 32, clock: Callable[[], float] = time.monotonic,
) -> Reply:
    if not 0 < timeout_seconds <= 10 or not 1 <= max_reports <= 128:
        raise ValueError("A bounded reply deadline and report count are required.")
    deadline = clock() + timeout_seconds
    for _ in range(max_reports):
        remaining = deadline - clock()
        if remaining <= 0:
            break
        try:
            packet = source.read_report(remaining)
        except TimeoutError:
            break
        try:
            return parse_reply(packet, expected)
        except InvalidReply:
            continue
    raise ReplyTimeout("No matching reply within the bounded read.")


@dataclass(frozen=True)
class BatteryReading:
    percent: int
    charging: bool


def battery_reading(reply: Reply) -> BatteryReading:
    if reply.command != 0x04 or len(reply.payload) < 2 or reply.payload[0] > 100 or reply.payload[1] not in {0, 1}:
        raise InvalidReply("Battery data is unavailable.")
    return BatteryReading(reply.payload[0], reply.payload[1] == 1)


def firmware_version(reply: Reply) -> str | None:
    if reply.command not in {0x12, 0x1D} or len(reply.payload) < 2:
        raise InvalidReply("Firmware data is unavailable.")
    major, minor = reply.payload[:2]
    if major == minor == 0 or major == minor == 0xFF:
        return None
    # Candidate vendor display convention; exact-device fixtures remain required.
    return f"{major}.{minor:02x}"


def complemented_value(reply: Reply) -> int:
    if reply.command != 0x08 or len(reply.payload) != 2 or sum(reply.payload) & 0xFF != 0x55:
        raise InvalidReply("Invalid settings value checksum.")
    return reply.payload[0]


def polling_rate(reply: Reply) -> int | None:
    return POLLING_CODES.get(complemented_value(reply))


def dpi_value(reply: Reply) -> int | None:
    if reply.command != 0x08 or len(reply.payload) != 4 or sum(reply.payload) & 0xFF != 0x55:
        raise InvalidReply("Invalid DPI record checksum.")
    x_low, y_low, packed, _check = reply.payload
    nibble = packed & 0x0F
    if x_low != y_low or packed >> 4 != nibble:
        return None  # A scalar API cannot represent asymmetric axes safely.
    decoded = ((nibble << 2) | (nibble >> 2)) & 0x0F
    mode, page = decoded >> 2, decoded & 3
    parameters = {0: (10, 1), 2: (50, 201), 3: (100, 201)}
    if mode not in parameters:
        return None
    step, base = parameters[mode]
    value = (x_low + base + 256 * page) * step
    return value if 1 <= value <= 32000 else None

"""Offline parsing of AK820 Pro Studio control acknowledgements, not telemetry.

Reference: kabelklaus/ajazz-ak820-pro at
4b69f3cb57506f518e5b2f9f5f56e07e8b9411d6 (MIT).
Copyright (c) 2026 kabelklaus. See LICENSE.ajazz-ak820-pro.
No output packets, device opens or live reads are implemented.
"""

from dataclasses import dataclass


class InvalidControlAcknowledgement(ValueError):
    pass


@dataclass(frozen=True)
class ControlAcknowledgement:
    command: int
    subcommand: int


def parse_control_ack(payload: bytes, expected_command: int, expected_subcommand: int = 0) -> ControlAcknowledgement:
    """Accept only a matching normalized 64-byte FF13 payload.

    A successful command echo does not prove a setting was applied or persisted.
    Transport normalization must be descriptor-specific; do not guess report IDs.
    """
    if type(expected_command) is not int or expected_command not in {0x18, 0x13}:
        raise ValueError("Only known START/lighting acknowledgements are supported.")
    if type(expected_subcommand) is not int or not 0 <= expected_subcommand <= 255:
        raise ValueError("A byte-sized subcommand is required.")
    if len(payload) != 64 or payload[:4] != bytes((0x04, expected_command, expected_subcommand, 0x01)):
        raise InvalidControlAcknowledgement("No matching control acknowledgement.")
    return ControlAcknowledgement(expected_command, expected_subcommand)

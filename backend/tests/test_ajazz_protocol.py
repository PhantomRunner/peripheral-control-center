"""Synthetic acknowledgement payloads; no real HID hardware or transport."""

import pytest

from pcc.drivers.protocols.ajazz_readonly import InvalidControlAcknowledgement, parse_control_ack


def ack(command=0x18, subcommand=0, status=1):
    return bytes((4, command, subcommand, status)) + bytes(60)


@pytest.mark.parametrize("command", [0x18, 0x13])
def test_matching_command_echo_is_only_an_ack(command):
    result = parse_control_ack(ack(command), command)
    assert result.command == command
    assert result.subcommand == 0
    assert not hasattr(result, "battery_percent")
    assert not hasattr(result, "firmware_version")
    assert not hasattr(result, "rgb")


@pytest.mark.parametrize("payload", [b"", ack()[:-1], ack() + b"\0", b"\0" + ack(), ack(0x13), ack(subcommand=1), ack(status=0), bytes((0x55, 0x18, 0, 1)) + bytes(60)])
def test_unmatched_or_other_protocol_payloads_are_rejected(payload):
    with pytest.raises(InvalidControlAcknowledgement):
        parse_control_ack(payload, 0x18)


@pytest.mark.parametrize("command", [0x02, 0x09, 0xF0, 0xFF, True])
def test_reset_save_unknown_and_noninteger_ack_modes_are_not_exposed(command):
    with pytest.raises(ValueError):
        parse_control_ack(ack(), command)

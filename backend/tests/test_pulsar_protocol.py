"""Synthetic replies only; none are presented as captured PSSTX21 telemetry."""

import pytest

from pcc.drivers.protocols.pulsar_readonly import (
    ExpectedReply, InvalidReply, Reply, ReplyTimeout, battery_reading, dpi_value,
    firmware_version, parse_reply, polling_rate, receive_reply,
)


def packet(command: int, payload: bytes = b"", address: int = 0, status: int = 0) -> bytes:
    raw = bytearray(17)
    raw[0] = 8
    raw[1] = command
    raw[2] = status
    raw[3:5] = address.to_bytes(2, "big")
    raw[5] = len(payload)
    raw[6:6 + len(payload)] = payload
    raw[16] = (0x55 - sum(raw[:16])) & 0xFF
    return bytes(raw)


def pair(value: int) -> bytes:
    return bytes((value, (0x55 - value) & 0xFF))


def stage(value: str) -> Reply:
    raw = bytes.fromhex(value)
    return Reply(8, raw + bytes(((0x55 - sum(raw)) & 0xFF,)))


@pytest.mark.parametrize("raw", [b"", b"\0" * 17, packet(4, b"\x32\x00")[:-1], packet(4, b"\x32\x00") + b"\0", packet(4, b"\x32\x00", status=1)])
def test_invalid_framing_and_failed_status_are_rejected(raw: bytes):
    with pytest.raises(InvalidReply):
        parse_reply(raw, ExpectedReply(4))


def test_wrong_command_address_and_length_are_rejected():
    for raw in (packet(0x0A), packet(8, pair(1), address=2), packet(8, b"\1", address=0)):
        with pytest.raises(InvalidReply):
            parse_reply(raw, ExpectedReply(8, address=0, length=2))


def test_bad_checksum_and_oversize_payload_are_rejected():
    raw = bytearray(packet(4, b"\x32\x00"))
    raw[-1] ^= 1
    with pytest.raises(InvalidReply):
        parse_reply(bytes(raw), ExpectedReply(4))
    raw = bytearray(packet(4))
    raw[5] = 11
    raw[16] = (0x55 - sum(raw[:16])) & 0xFF
    with pytest.raises(InvalidReply):
        parse_reply(bytes(raw), ExpectedReply(4))


def test_battery_zero_is_real_data_but_invalid_percent_is_unavailable():
    assert battery_reading(parse_reply(packet(4, b"\0\1"), ExpectedReply(4))).percent == 0
    assert battery_reading(Reply(4, b"\x32\1")).charging is True
    for payload in (b"", b"\x32", b"\x65\0", b"\x32\2"):
        with pytest.raises(InvalidReply):
            battery_reading(Reply(4, payload))


def test_firmware_uses_candidate_vendor_minor_format_without_default_version():
    assert firmware_version(Reply(0x12, b"\3\3")) == "3.03"
    assert firmware_version(Reply(0x1D, b"\2\x24")) == "2.24"
    assert firmware_version(Reply(0x12, b"\0\0")) is None
    assert firmware_version(Reply(0x12, b"\xff\xff")) is None
    with pytest.raises(InvalidReply):
        firmware_version(Reply(0x12, b"\3"))


@pytest.mark.parametrize(("code", "rate"), [(1, 1000), (2, 500), (4, 250), (8, 125), (16, 2000), (32, 4000), (64, 8000), (0, None), (255, None)])
def test_polling_codes_never_default_to_1000(code: int, rate: int | None):
    assert polling_rate(Reply(8, pair(code))) == rate


@pytest.mark.parametrize(("raw", "dpi"), [("27 27 00", 400), ("4f 4f 00", 800), ("9f 9f 00", 1600), ("3f 3f 44", 3200), ("37 37 22", 12800), ("77 77 33", 32000)])
def test_reference_dpi_examples_are_offline_only(raw: str, dpi: int):
    assert dpi_value(stage(raw)) == dpi


@pytest.mark.parametrize("raw", ["27 28 00", "27 27 01", "27 27 11", "ff ff ff"])
def test_unknown_or_asymmetric_dpi_never_becomes_a_scalar(raw: str):
    assert dpi_value(stage(raw)) is None


def test_corrupt_settings_record_is_rejected():
    with pytest.raises(InvalidReply):
        polling_rate(Reply(8, b"\1\1"))
    with pytest.raises(InvalidReply):
        dpi_value(Reply(8, bytes.fromhex("27 27 00 00")))


def test_fake_input_source_skips_events_and_foreign_replies():
    class FakeSource:
        def __init__(self):
            self.reports = iter([packet(0x0A), b"mouse input", packet(8, pair(2), address=4), packet(8, pair(1), address=0)])
            self.deadlines = []

        def read_report(self, timeout_seconds: float) -> bytes:
            self.deadlines.append(timeout_seconds)
            return next(self.reports)

    source = FakeSource()
    now = iter([0.0, 0.1, 0.2, 0.3, 0.4])
    reply = receive_reply(source, ExpectedReply(8, 0, 2), clock=lambda: next(now))
    assert polling_rate(reply) == 1000
    assert source.deadlines == pytest.approx([0.9, 0.8, 0.7, 0.6])


def test_endless_events_have_a_bounded_count():
    class FakeSource:
        calls = 0
        def read_report(self, timeout_seconds: float) -> bytes:
            self.calls += 1
            return packet(0x0A)

    source = FakeSource()
    with pytest.raises(ReplyTimeout):
        receive_reply(source, ExpectedReply(4), max_reports=3, clock=lambda: 0.0)
    assert source.calls == 3


@pytest.mark.parametrize("command", [0x07, 0x09, 0x0F, 0xFF])
def test_write_reset_and_unknown_reply_types_are_not_exposed(command: int):
    with pytest.raises(ValueError):
        ExpectedReply(command)

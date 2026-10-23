"""No hardware access: synthetic replies and mocked descriptors only."""

import json
from collections import Counter
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pcc.diagnostics import pulsar_config_probe as probe
from pcc.drivers.protocols.pulsar_readonly import InvalidReply, Reply, ReplyTimeout


def pair(value: int) -> bytes:
    return bytes((value, (0x55 - value) & 255))


class FakeTransport:
    def __init__(self, changes=None):
        self.sent = []
        self.counts = Counter()
        self.changes = changes or {}

    def exchange(self, query):
        self.sent.append(query)
        self.counts[query] += 1
        payload = {
            probe.ConfigQuery.IDENTITY: bytes.fromhex("00 00 00 00 57 27 05 00"),
            probe.ConfigQuery.PROFILE: b"\0",
            probe.ConfigQuery.STAGE_COUNT: pair(4),
            probe.ConfigQuery.ACTIVE_STAGE: pair(2),
            probe.ConfigQuery.POLLING: pair(1),
            probe.ConfigQuery.DPI_2: bytes.fromhex("9f 9f 00 17"),
        }[query]
        payload = self.changes.get((query, self.counts[query]), payload)
        return Reply(query.value[0], payload)


def test_default_plan_has_no_device_or_process_access(monkeypatch, capsys):
    discover = Mock(side_effect=AssertionError("Plan must not discover/open hardware"))
    monkeypatch.setattr(probe, "discover_target", discover)
    assert probe.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["device_io"] is False
    assert plan["maximum_output_reports"] == 12
    assert plan["retries"] == 0
    assert plan["requires_separate_unvalidated_read_approval"] is True
    assert plan["settings_adapter_activation"] is False
    assert plan["queries"][0]["packet_hex"] == "08 01 00 00 00 08 13 57 9b df 00 00 00 00 00 00 60"
    discover.assert_not_called()


@pytest.mark.parametrize("value", [1, 7, 8, 9, 15, 255, (8, 0xE1, 8), b"packet", True])
def test_only_typed_fixed_queries_are_encodable(value):
    with pytest.raises(ValueError):
        probe.query_packet(value)


def test_packet_allowlist_contains_only_exact_nonprivate_ranges():
    packets = [probe.query_packet(query) for query in probe.ConfigQuery]
    assert {packet[1] for packet in packets} == {1, 8, 14}
    assert all(len(packet) == 17 and sum(packet) & 255 == 0x55 for packet in packets)
    ranges = [(int.from_bytes(p[3:5], "big"), p[5]) for p in packets if p[1] == 8]
    assert ranges == [(0, 2), (2, 2), (4, 2), (12, 4), (16, 4), (20, 4), (24, 4), (28, 4), (32, 4)]


def test_current_profile_only_and_no_adapter_activation_or_private_reply_output():
    transport = FakeTransport()
    result = probe.observe(transport)
    assert transport.sent == [
        probe.ConfigQuery.IDENTITY, probe.ConfigQuery.PROFILE, probe.ConfigQuery.STAGE_COUNT,
        probe.ConfigQuery.ACTIVE_STAGE, probe.ConfigQuery.POLLING, probe.ConfigQuery.DPI_2,
        probe.ConfigQuery.POLLING, probe.ConfigQuery.DPI_2, probe.ConfigQuery.ACTIVE_STAGE,
        probe.ConfigQuery.STAGE_COUNT, probe.ConfigQuery.PROFILE, probe.ConfigQuery.IDENTITY,
    ]
    assert result["observed"] == {"dpi_candidate": 1600, "stored_polling_rate_hz_candidate": 1000}
    assert result["adapter_enabled"] is False and result["settings_writes"] == 0
    assert result["setting_records"] == {"polling_hex": "01 54", "active_dpi_hex": "9f 9f 00 17"}
    assert "nonce" not in json.dumps(result)


@pytest.mark.parametrize("payload", [b"", b"\0" * 6, bytes.fromhex("00 00 00 00 57 03 05"), bytes.fromhex("00 00 00 00 57 27 01")])
def test_wrong_model_or_transport_stops_before_any_memory_read(payload):
    transport = FakeTransport({(probe.ConfigQuery.IDENTITY, 1): payload})
    with pytest.raises((probe.ProbeBlocked, InvalidReply)):
        probe.observe(transport)
    assert transport.sent == [probe.ConfigQuery.IDENTITY]


@pytest.mark.parametrize(("query", "payload"), [
    (probe.ConfigQuery.PROFILE, b"\4"),
    (probe.ConfigQuery.STAGE_COUNT, pair(0)),
    (probe.ConfigQuery.STAGE_COUNT, pair(7)),
    (probe.ConfigQuery.ACTIVE_STAGE, pair(4)),
    (probe.ConfigQuery.POLLING, pair(0)),
    (probe.ConfigQuery.POLLING, b"\1\1"),
    (probe.ConfigQuery.DPI_2, bytes.fromhex("9f 9e 00 18")),
])
def test_unknown_or_corrupt_values_abort_without_defaults_or_retry(query, payload):
    transport = FakeTransport({(query, 1): payload})
    with pytest.raises((probe.ProbeBlocked, InvalidReply)):
        probe.observe(transport)
    assert transport.counts[query] == 1


@pytest.mark.parametrize(("query", "payload"), [
    (probe.ConfigQuery.POLLING, pair(2)),
    (probe.ConfigQuery.DPI_2, bytes.fromhex("4f 4f 00 b7")),
    (probe.ConfigQuery.ACTIVE_STAGE, pair(1)),
    (probe.ConfigQuery.STAGE_COUNT, pair(5)),
    (probe.ConfigQuery.PROFILE, b"\1"),
    (probe.ConfigQuery.IDENTITY, bytes.fromhex("00 00 00 00 57 03 05")),
])
def test_final_snapshot_must_match_each_initial_observation(query, payload):
    transport = FakeTransport({(query, 2): payload})
    with pytest.raises(probe.ProbeBlocked):
        probe.observe(transport)
    assert len(transport.sent) <= 12
    assert transport.counts[query] == 2


def test_real_transport_logic_has_fixed_budget_and_no_retry(monkeypatch):
    opened = SimpleNamespace(descriptor=99, target=SimpleNamespace(verify_cached_identity=Mock()), numbers=frozenset({42}))
    monkeypatch.setattr(probe, "check_competitors", Mock())
    write = Mock(return_value=17)
    monkeypatch.setattr(probe.os, "write", write)
    receive = Mock(return_value=Reply(14, b"\0"))
    monkeypatch.setattr(probe, "receive_reply", receive)
    transport = probe.ConfigHidraw(opened)
    for _ in range(12):
        transport.exchange(probe.ConfigQuery.PROFILE)
    with pytest.raises(probe.ProbeBlocked, match="budget"):
        transport.exchange(probe.ConfigQuery.PROFILE)
    assert write.call_count == 12
    assert receive.call_args.kwargs == {"timeout_seconds": 0.5, "max_reports": 32}
    assert receive.call_args.args[1] == probe.ExpectedReply(14)
    transport = probe.ConfigHidraw(opened)
    write.reset_mock()
    write.return_value = 1
    with pytest.raises(probe.ProbeBlocked, match="Incomplete"):
        transport.exchange(probe.ConfigQuery.PROFILE)
    write.assert_called_once()


def test_timeout_stops_after_one_output(monkeypatch):
    opened = SimpleNamespace(descriptor=99, target=SimpleNamespace(verify_cached_identity=Mock()), numbers=frozenset({42}))
    monkeypatch.setattr(probe, "check_competitors", Mock())
    write = Mock(return_value=17)
    monkeypatch.setattr(probe.os, "write", write)
    monkeypatch.setattr(probe, "receive_reply", Mock(side_effect=ReplyTimeout))
    with pytest.raises(ReplyTimeout):
        probe.observe(probe.ConfigHidraw(opened))
    write.assert_called_once()


def test_execute_requires_operator_confirmation_before_discovery(monkeypatch, capsys):
    discover = Mock(side_effect=AssertionError("Missing closure confirmation"))
    monkeypatch.setattr(probe, "discover_target", discover)
    assert probe.main(["--execute"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    discover.assert_not_called()


def test_discovery_error_redacts_paths_and_never_opens_hid(monkeypatch, capsys):
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "discover_target", Mock(side_effect=PermissionError("/private/serial")))
    opened = Mock(side_effect=AssertionError("Must not open"))
    monkeypatch.setattr(probe, "open_probe", opened)
    assert probe.main(["--execute", "--vendor-tools-closed"]) == 2
    assert "private" not in capsys.readouterr().out
    opened.assert_not_called()


def framed_identity(*, length=8, status=0, checksum_valid=True):
    packet = bytearray.fromhex("08 01 00 00 00 08 13 57 9b df 57 27 05 00 00 00 00")
    packet[2], packet[5] = status, length
    packet[-1] = (0x55 - sum(packet[:-1])) & 255
    if not checksum_valid:
        packet[-1] ^= 1
    return bytes(packet)


@pytest.mark.parametrize(("packet", "kind", "phase", "details"), [
    (None, "reply_timeout", "receive", {"reports_received": 0, "matching_command_reports": 0}),
    (framed_identity(length=0), "invalid_reply", "decode", {"last_payload_length": 0, "expected_identity_fields_present": True}),
    (framed_identity(status=1), "reply_timeout", "receive", {"nonzero_status_reports": 1}),
    (framed_identity(checksum_valid=False), "reply_timeout", "receive", {"bad_checksum_reports": 1}),
    (framed_identity(length=11), "reply_timeout", "receive", {"last_payload_length": 11}),
])
def test_cli_failure_reports_stage_counts_and_safe_reply_metadata_without_retry(monkeypatch, capsys, packet, kind, phase, details):
    reader = Mock(side_effect=[packet, TimeoutError()] if packet is not None else TimeoutError())
    opened = SimpleNamespace(descriptor=99, target=SimpleNamespace(verify_cached_identity=Mock()),
                             numbers=frozenset({42}), read_report=reader)
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "discover_target", lambda: object())
    monkeypatch.setattr(probe, "open_probe", lambda *args, **kwargs: nullcontext(opened))
    monkeypatch.setattr(probe, "process_deadline", nullcontext)
    monkeypatch.setattr(probe, "check_competitors", Mock())
    write = Mock(return_value=17)
    monkeypatch.setattr(probe.os, "write", write)
    assert probe.main(["--execute", "--vendor-tools-closed"]) == 2
    text = capsys.readouterr().out
    result = json.loads(text)
    assert result["failure_kind"] == kind
    diagnostic = result["diagnostics"]
    assert diagnostic["last_query"] == "identity" and diagnostic["phase"] == phase
    assert diagnostic["output_reports_attempted"] == diagnostic["output_reports_completed"] == 1
    assert all(diagnostic["reply_diagnostics"][key] == value for key, value in details.items())
    assert "13 57 9b df" not in text and "13579bdf" not in text
    assert "cid" not in text and "payload_hex" not in text
    write.assert_called_once()


@pytest.mark.parametrize("error", [PermissionError("/private/machine/serial"), OSError("/private/machine/serial")])
def test_open_failure_is_distinct_from_a_failed_query_and_has_no_outputs(monkeypatch, capsys, error):
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "discover_target", lambda: object())
    monkeypatch.setattr(probe, "open_probe", Mock(side_effect=error))
    monkeypatch.setattr(probe, "process_deadline", nullcontext)
    assert probe.main(["--execute", "--vendor-tools-closed"]) == 2
    text = capsys.readouterr().out
    result = json.loads(text)
    assert result["failure_kind"] == ("permission_denied" if isinstance(error, PermissionError) else "io_error")
    assert result["diagnostics"] == {"phase": "open", "last_query": None, "output_reports_attempted": 0, "output_reports_completed": 0}
    assert "private" not in text and "serial" not in text

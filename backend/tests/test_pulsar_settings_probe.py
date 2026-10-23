"""Fixed write experiment: exclusively synthetic IO, never real hardware."""

import json
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pcc.diagnostics import pulsar_settings_probe as probe
from pcc.drivers.protocols.pulsar_readonly import Reply


def frame(command, payload=b"", address=0, status=0):
    packet = bytearray(17)
    packet[:3] = bytes((8, command, status))
    packet[3:5] = address.to_bytes(2, "big")
    packet[5] = len(payload)
    packet[6:6 + len(payload)] = payload
    packet[-1] = (0x55 - sum(packet[:-1])) & 255
    return bytes(packet)


class FakeDevice:
    def __init__(self, *, profile=0, fail_write=0, ignore_test=False):
        self.profile, self.fail_write, self.ignore_test = profile, fail_write, ignore_test
        self.records = {0: bytes.fromhex("01 54"), 2: bytes.fromhex("05 50"),
                        4: bytes.fromhex("02 53"), 20: bytes.fromhex("77 77 00 67")}
        self.outputs = []
        self.pending = []
        self.write_count = 0
        self.opened = SimpleNamespace(target=SimpleNamespace(verify_cached_identity=Mock()),
                                      descriptor=99, numbers=frozenset({42}), read_report=self.read)

    def write(self, descriptor, packet):
        assert descriptor == 99
        assert len(packet) == 17 and sum(packet) & 255 == 0x55
        self.outputs.append(packet)
        command = packet[1]
        address = int.from_bytes(packet[3:5], "big")
        if command == 1:
            self.pending.append(frame(1, bytes.fromhex("00 00 00 00 57 27 05 00")))
        elif command == 14:
            self.pending.append(frame(14, bytes((self.profile,))))
        elif command == 8:
            assert (address, packet[5]) in {(0, 2), (2, 2), (4, 2), (20, 4)}
            self.pending.append(frame(8, self.records[address], address))
        elif command == 7:
            self.write_count += 1
            assert (address, packet[5]) in {(0, 2), (20, 4)}
            if not self.ignore_test:
                self.records[address] = packet[6:6 + packet[5]]
            if self.write_count != self.fail_write:
                self.pending.append(frame(7))
        else:
            pytest.fail(f"Forbidden fake output command: {command}")
        return len(packet)

    def read(self, timeout_seconds):
        assert 0 < timeout_seconds <= 0.5
        if not self.pending:
            raise TimeoutError
        return self.pending.pop(0)


@pytest.fixture
def fake_io(monkeypatch):
    monkeypatch.setattr(probe, "check_competitors", Mock())
    monkeypatch.setattr("pcc.diagnostics.pulsar_config_probe.check_competitors", Mock())
    def make(**kwargs):
        device = FakeDevice(**kwargs)
        monkeypatch.setattr(probe.os, "write", device.write)
        return device, probe.SettingsHidraw(device.opened)
    return make


def test_default_plan_is_inert_and_discloses_fixed_settings_memory_writes(monkeypatch, capsys):
    discover = Mock(side_effect=AssertionError("Plan must not inspect or open hardware"))
    monkeypatch.setattr(probe, "discover_target", discover)
    assert probe.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["device_io"] is False and plan["requires_separate_settings_memory_write_approval"] is True
    assert plan["settings_writes_may_persist"] is True
    assert plan["maximum_output_reports"] == 40 and plan["maximum_settings_write_reports"] == 4
    assert plan["settings_adapter_activation"] is False and plan["retries"] == 0
    discover.assert_not_called()


@pytest.mark.parametrize("action", [7, (20, b"\0" * 4), b"arbitrary", True])
def test_raw_packets_and_arbitrary_settings_cannot_be_encoded(action):
    with pytest.raises(ValueError):
        probe.write_packet(action)


def test_packet_allowlist_has_only_four_exact_requested_setting_records():
    packets = [probe.write_packet(action) for action in probe.FixedWrite]
    assert [packet[1] for packet in packets] == [7] * 4
    assert [(int.from_bytes(p[3:5], "big"), p[5], p[6:6 + p[5]].hex(" ")) for p in packets] == [
        (20, 4, "4f 4f 00 b7"), (0, 2, "02 53"), (20, 4, "77 77 00 67"), (0, 2, "01 54"),
    ]
    assert all(len(p) == 17 and sum(p) & 255 == 0x55 for p in packets)


def test_complete_fake_experiment_verifies_final_combined_state_and_explicit_restoration(fake_io):
    device, transport = fake_io()
    result = probe.observe(transport)
    assert result["status"] == "settings_test_verified_and_restored"
    assert result["tested"] == {"dpi": 800, "polling_rate_hz": 500}
    assert result["restored"] == {"dpi": 1200, "polling_rate_hz": 1000}
    assert result["adapter_enabled"] is False
    assert len(device.outputs) == 40
    writes = [(index, packet) for index, packet in enumerate(device.outputs) if packet[1] == 7]
    assert [index for index, _packet in writes] == [12, 13, 26, 27]
    assert [packet for _index, packet in writes] == [probe.write_packet(action) for action in probe.FixedWrite]
    assert device.records[0] == bytes.fromhex("01 54") and device.records[20] == bytes.fromhex("77 77 00 67")
    diagnostics = transport.diagnostics()
    assert diagnostics["output_reports_attempted"] == diagnostics["output_reports_completed"] == 40
    assert diagnostics["settings_writes_attempted"] == diagnostics["settings_writes_completed"] == 4


def test_unexpected_profile_aborts_before_any_setting_output(fake_io):
    device, transport = fake_io(profile=1)
    with pytest.raises(probe.ProbeBlocked):
        probe.observe(transport)
    assert len(device.outputs) == 12 and device.write_count == 0


def test_acknowledged_but_ignored_settings_do_not_trigger_restore_or_success(fake_io):
    device, transport = fake_io(ignore_test=True)
    with pytest.raises(probe.ProbeBlocked):
        probe.observe(transport)
    assert device.write_count == 2
    assert len(device.outputs) == 26


@pytest.mark.parametrize("failed", [1, 2, 3, 4])
def test_unconfirmed_write_stops_without_retry_or_error_handler_restoration(fake_io, failed):
    device, transport = fake_io(fail_write=failed)
    with pytest.raises(probe.ReplyTimeout):
        probe.observe(transport)
    assert device.write_count == failed
    writes = [packet for packet in device.outputs if packet[1] == 7]
    assert writes == [probe.write_packet(action) for action in tuple(probe.FixedWrite)[:failed]]
    assert transport.diagnostics()["settings_writes_attempted"] == failed


def test_write_order_and_budget_cannot_be_replayed(fake_io):
    device, transport = fake_io()
    with pytest.raises(probe.ProbeBlocked, match="order"):
        transport.write_setting(probe.FixedWrite.RESTORE_DPI_1200)
    assert not device.outputs
    probe.observe(transport)
    with pytest.raises(probe.ProbeBlocked):
        transport.write_setting(probe.FixedWrite.TEST_DPI_800)
    with pytest.raises(probe.ProbeBlocked):
        transport.exchange(probe.ConfigQuery.PROFILE)
    assert len(device.outputs) == 40


@pytest.mark.parametrize("packet", [b"", frame(8), frame(7, status=1), bytes(17)])
def test_invalid_or_foreign_ack_never_verifies_a_write(packet):
    reader = Mock(side_effect=[packet, TimeoutError()])
    with pytest.raises(probe.ReplyTimeout):
        probe.receive_write_ack(SimpleNamespace(read_report=reader))


def test_unrelated_ack_input_is_bounded():
    reader = Mock(return_value=frame(8))
    with pytest.raises(probe.ReplyTimeout):
        probe.receive_write_ack(SimpleNamespace(read_report=reader))
    assert reader.call_count == 32


def test_execute_requires_confirmation_and_refuses_root(monkeypatch, capsys):
    discover = Mock(side_effect=AssertionError("Must not inspect/open"))
    monkeypatch.setattr(probe, "discover_target", discover)
    assert probe.main(["--execute"]) == 2
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)
    assert probe.main(["--execute", "--vendor-tools-closed"]) == 2
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["settings_may_have_changed"] is False
    discover.assert_not_called()


def test_watchdog_restores_handlers_without_waiting(monkeypatch):
    previous = object()
    handler = Mock(return_value=previous)
    timer = Mock()
    monkeypatch.setattr(probe.signal, "getitimer", lambda which: (0.0, 0.0))
    monkeypatch.setattr(probe.signal, "signal", handler)
    monkeypatch.setattr(probe.signal, "setitimer", timer)
    with pytest.raises(probe.ProbeBlocked):
        with probe.experiment_deadline():
            handler.call_args_list[0].args[1](None, None)
    assert timer.call_args_list[0].args == (probe.signal.ITIMER_REAL, 30)
    assert timer.call_args_list[-1].args == (probe.signal.ITIMER_REAL, 0)
    assert handler.call_args_list[-1].args == (probe.signal.SIGALRM, previous)


def test_cli_reports_uncertain_state_and_closes_without_more_output_after_failure(fake_io, monkeypatch, capsys):
    device, _transport = fake_io(fail_write=1)
    closed = Mock()
    @contextmanager
    def opened(*args, **kwargs):
        assert kwargs == {"vendor_tools_closed": True}
        try:
            yield device.opened
        finally:
            closed()
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "discover_target", lambda: object())
    monkeypatch.setattr(probe, "open_probe", opened)
    monkeypatch.setattr(probe, "experiment_deadline", nullcontext)
    assert probe.main(["--execute", "--vendor-tools-closed"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["settings_may_have_changed"] is True
    assert result["diagnostics"]["phase"] == "test_dpi_800"
    assert result["diagnostics"]["output_reports_completed"] == 13
    assert device.write_count == 1
    closed.assert_called_once()

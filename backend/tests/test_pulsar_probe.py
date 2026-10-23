"""Probe behavior is tested exclusively with fake transports and temporary sysfs/proc trees."""

import json
import os
import stat
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pcc.diagnostics import pulsar_probe as probe
from pcc.drivers.protocols.pulsar_readonly import InvalidReply, ReplyTimeout


def reply(command: int, payload: bytes) -> bytes:
    data = bytearray(17)
    data[0:2] = bytes((8, command))
    data[5] = len(payload)
    data[6:6 + len(payload)] = payload
    data[16] = (0x55 - sum(data[:16])) & 0xFF
    return bytes(data)


class FakeTransport:
    def __init__(self, reports: list[bytes]):
        self.reports = iter(reports)
        self.sent = []

    def send_query(self, query: probe.FixedQuery):
        self.sent.append(probe.query_packet(query))

    def read_report(self, timeout_seconds: float) -> bytes:
        try:
            return next(self.reports)
        except StopIteration:
            raise TimeoutError from None


def test_default_plan_performs_no_device_or_process_io(monkeypatch: pytest.MonkeyPatch, capsys):
    discover = Mock(side_effect=AssertionError("Default mode must not discover/open hardware"))
    monkeypatch.setattr(probe, "discover_target", discover)
    monkeypatch.setattr(probe.os, "open", Mock(side_effect=AssertionError("No device opens in plan mode")))
    assert probe.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["device_io"] is False
    assert result["maximum_output_reports"] == 2
    assert result["retries"] == 0
    assert result["requires_separate_unvalidated_read_approval"] is True
    assert [query["packet_hex"] for query in result["queries"]] == [
        "08 04 00 00 00 00 00 00 00 00 00 00 00 00 00 00 49",
        "08 12 00 00 00 00 00 00 00 00 00 00 00 00 00 00 3b",
    ]
    discover.assert_not_called()


@pytest.mark.parametrize("command", [0x01, 0x02, 0x03, 0x07, 0x08, 0x09, 0x0F, 0x1D, b"\x04", True])
def test_initialization_memory_profile_reset_and_arbitrary_queries_are_not_available(command):
    with pytest.raises(ValueError):
        probe.query_packet(command)


def test_probe_sends_only_the_two_known_queries_and_does_not_enable_any_adapter():
    transport = FakeTransport([reply(4, b"\0\1"), reply(0x12, b"\3\3")])
    result = probe.observe(transport)
    assert [packet[1] for packet in transport.sent] == [4, 0x12]
    assert all(len(packet) == 17 and sum(packet) & 255 == 0x55 for packet in transport.sent)
    assert result["observed"] == {"battery_percent": 0, "charging": True, "mouse_firmware_candidate": "3.03"}
    assert result["device_model_verified"] is False
    assert result["adapter_enabled"] is False


def test_timeout_stops_without_retry_or_second_query():
    transport = FakeTransport([])
    with pytest.raises(ReplyTimeout):
        probe.observe(transport)
    assert len(transport.sent) == 1


def test_invalid_battery_stops_before_any_more_output():
    transport = FakeTransport([reply(4, b"\xff\0")])
    with pytest.raises(InvalidReply):
        probe.observe(transport)
    assert len(transport.sent) == 1


def test_unused_reply_bytes_are_not_disclosed():
    transport = FakeTransport([reply(4, b"\x32\0PRIVATE!"), reply(0x12, b"\3\3SECRET!!")])
    text = json.dumps(probe.observe(transport))
    assert "PRIVATE" not in text and "SECRET" not in text
    assert "serial" not in text and "/dev/" not in text


def make_sysfs(root: Path, name: str = "hidraw0", descriptor: bytes = b"test descriptor"):
    usb = root / name / "usb"
    interface = usb / "interface"
    hid = interface / "hid"
    hid.mkdir(parents=True)
    (usb / "idVendor").write_text("3710\n")
    (usb / "idProduct").write_text("5406\n")
    (usb / "busnum").write_text("1\n")
    (usb / "devnum").write_text("9\n")
    (interface / "bInterfaceNumber").write_text("01\n")
    (hid / "uevent").write_text("HID_ID=0003:00003710:00005406\nHID_UNIQ=private serial\n")
    (hid / "report_descriptor").write_bytes(descriptor)
    entry = root / "hidraw" / name
    entry.mkdir(parents=True)
    (entry / "device").symlink_to(hid, target_is_directory=True)
    return hid


def test_target_selection_requires_exact_ids_interface_and_descriptor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import hashlib
    hid = make_sysfs(tmp_path)
    monkeypatch.setattr(probe, "DESCRIPTOR_SHA256", hashlib.sha256(b"test descriptor").hexdigest())
    target = probe.discover_target(tmp_path / "hidraw", tmp_path / "dev")
    assert target.node == tmp_path / "dev" / "hidraw0"
    assert str(tmp_path) not in repr(target)
    (hid / "report_descriptor").write_bytes(b"changed revision")
    with pytest.raises(probe.ProbeBlocked):
        target.verify_cached_identity()


def test_multiple_matching_receivers_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import hashlib
    make_sysfs(tmp_path, "hidraw0")
    make_sysfs(tmp_path, "hidraw1")
    monkeypatch.setattr(probe, "DESCRIPTOR_SHA256", hashlib.sha256(b"test descriptor").hexdigest())
    with pytest.raises(probe.ProbeBlocked, match="exactly one"):
        probe.discover_target(tmp_path / "hidraw", tmp_path / "dev")


def test_a_competing_character_device_handle_blocks_access(tmp_path: Path):
    # /dev/null is stat-ed only, never opened; it stands in for a device number.
    other = tmp_path / str(os.getpid() + 1000000) / "fd"
    other.mkdir(parents=True)
    (other / "7").symlink_to("/dev/null")
    with pytest.raises(probe.ProbeBlocked, match="Another process"):
        probe.check_competitors(frozenset({Path("/dev/null").stat().st_rdev}), tmp_path)


def test_uninspectable_current_user_process_is_not_mistaken_for_verified_ownership(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    other = tmp_path / str(os.getpid() + 1000000) / "fd"
    other.mkdir(parents=True)
    iterdir = Path.iterdir

    def deny(path):
        if path == other:
            raise PermissionError("private process path")
        return iterdir(path)

    monkeypatch.setattr(Path, "iterdir", deny)
    assert probe.check_competitors(frozenset({1}), tmp_path) == 1


def test_execute_requires_closed_vendor_tools_before_discovery(monkeypatch: pytest.MonkeyPatch, capsys):
    discover = Mock(side_effect=AssertionError("Must not discover"))
    monkeypatch.setattr(probe, "discover_target", discover)
    assert probe.main(["--execute"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    discover.assert_not_called()


def test_root_and_preflight_never_open_hid(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)
    monkeypatch.setattr(probe, "open_probe", Mock(side_effect=AssertionError("Must not open HID")))
    assert probe.main(["--execute", "--vendor-tools-closed"]) == 2
    assert "root" in capsys.readouterr().out


def test_preflight_only_inspects_metadata_and_handles(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "discover_target", lambda: object())
    monkeypatch.setattr(probe, "device_numbers", lambda target: frozenset({1, 2}))
    check = Mock(return_value=0)
    monkeypatch.setattr(probe, "check_competitors", check)
    monkeypatch.setattr(probe, "open_probe", Mock(side_effect=AssertionError("Must not open HID")))
    assert probe.main(["--check-access"]) == 0
    assert json.loads(capsys.readouterr().out)["device_io"] is False
    check.assert_called_once_with(frozenset({1, 2}))


def test_incomplete_preflight_reports_the_need_for_manual_tool_closure(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "discover_target", lambda: object())
    monkeypatch.setattr(probe, "device_numbers", lambda target: frozenset({1}))
    monkeypatch.setattr(probe, "check_competitors", lambda numbers: 4)
    assert probe.main(["--check-access"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "manual_tool_closure_required"
    assert result["ownership_verified"] is False
    assert result["device_io"] is False


def test_io_errors_do_not_disclose_machine_paths(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "discover_target", Mock(side_effect=PermissionError("/private/serial-machine-path")))
    assert probe.main(["--check-access"]) == 2
    text = capsys.readouterr().out
    assert "private" not in text and "serial-machine-path" not in text


@pytest.fixture
def fake_device(monkeypatch: pytest.MonkeyPatch):
    info = SimpleNamespace(st_mode=stat.S_IFCHR | 0o600, st_rdev=42)
    target = SimpleNamespace(node=Mock(lstat=Mock(return_value=info)), verify_cached_identity=Mock())
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "DeviceOwnership", lambda: SimpleNamespace(claim=lambda device_id: nullcontext()))
    monkeypatch.setattr(probe, "device_numbers", lambda selected: frozenset({42}))
    monkeypatch.setattr(probe, "check_competitors", Mock())
    monkeypatch.setattr(probe.os, "open", Mock(return_value=99))
    monkeypatch.setattr(probe.os, "fstat", Mock(return_value=info))
    close = Mock()
    write = Mock(return_value=17)
    monkeypatch.setattr(probe.os, "close", close)
    monkeypatch.setattr(probe.os, "write", write)
    return target, close, write


def test_fake_open_has_no_implicit_output_and_always_closes(fake_device):
    target, close, write = fake_device
    with pytest.raises(RuntimeError):
        with probe.open_probe(target, vendor_tools_closed=True):
            write.assert_not_called()
            raise RuntimeError("fake read failed")
    close.assert_called_once_with(99)
    write.assert_not_called()


def test_changed_node_is_closed_before_any_query(fake_device, monkeypatch: pytest.MonkeyPatch):
    target, close, write = fake_device
    monkeypatch.setattr(probe.os, "fstat", lambda descriptor: SimpleNamespace(st_mode=stat.S_IFCHR, st_rdev=43))
    with pytest.raises(probe.ProbeBlocked, match="node changed"):
        with probe.open_probe(target, vendor_tools_closed=True):
            pytest.fail("Must not yield a changed device")
    close.assert_called_once_with(99)
    write.assert_not_called()


def test_real_transport_logic_has_an_absolute_two_output_budget(fake_device):
    target, _close, write = fake_device
    transport = probe.HidrawProbe(target, 99, frozenset({42}))
    transport.send_query(probe.FixedQuery.BATTERY)
    transport.send_query(probe.FixedQuery.MOUSE_FIRMWARE)
    with pytest.raises(probe.ProbeBlocked, match="budget"):
        transport.send_query(probe.FixedQuery.BATTERY)
    assert write.call_args_list == [
        ((99, probe.query_packet(probe.FixedQuery.BATTERY)),),
        ((99, probe.query_packet(probe.FixedQuery.MOUSE_FIRMWARE)),),
    ]


def test_incomplete_output_is_not_retried(fake_device):
    target, _close, write = fake_device
    write.return_value = 1
    transport = probe.HidrawProbe(target, 99, frozenset({42}))
    with pytest.raises(probe.ProbeBlocked, match="Incomplete"):
        probe.observe(transport)
    write.assert_called_once()


def test_open_requires_operator_tool_closure_even_if_visible_handles_look_clear(fake_device):
    target, close, write = fake_device
    with pytest.raises(probe.ProbeBlocked, match="operator"):
        with probe.open_probe(target):
            pytest.fail("No operator confirmation")
    close.assert_not_called()
    write.assert_not_called()


def test_process_deadline_restores_the_previous_handler_without_waiting(monkeypatch: pytest.MonkeyPatch):
    previous = object()
    handler = Mock(return_value=previous)
    timer = Mock()
    monkeypatch.setattr(probe.signal, "getitimer", lambda which: (0.0, 0.0))
    monkeypatch.setattr(probe.signal, "signal", handler)
    monkeypatch.setattr(probe.signal, "setitimer", timer)
    with pytest.raises(probe.ProbeBlocked, match="deadline"):
        with probe.process_deadline():
            handler.call_args_list[0].args[1](None, None)
    assert timer.call_args_list[0].args == (probe.signal.ITIMER_REAL, 8)
    assert timer.call_args_list[-1].args == (probe.signal.ITIMER_REAL, 0)
    assert handler.call_args_list[-1].args == (probe.signal.SIGALRM, previous)

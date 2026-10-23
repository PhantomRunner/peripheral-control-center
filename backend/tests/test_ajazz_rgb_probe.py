"""Fake-only FF13 experiment tests. No real HID, root or device commands."""

import hashlib
import json
import stat
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pcc.diagnostics import ajazz_rgb_probe as probe


def ack(command):
    return bytes((4, command, 0, 1)) + bytes(60)


class FakeFeatures:
    def __init__(self, replies=None):
        self.replies = iter(replies or [b"private serial data".ljust(64, b"!"), ack(0x18), ack(0x13), ack(2)])
        self.sent = []
        self.reads = 0

    def get_feature(self):
        self.reads += 1
        return next(self.replies)

    def send_feature(self, action):
        self.sent.append(probe.feature_payload(action))


def test_default_plan_never_discovers_or_opens_hardware(monkeypatch, capsys):
    discover = Mock(side_effect=AssertionError("Plan must not inspect devices"))
    monkeypatch.setattr(probe, "discover_target", discover)
    assert probe.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["device_io"] is False and plan["maximum_feature_sets"] == plan["maximum_feature_gets"] == 4
    assert plan["requires_separate_settings_write_approval"] is True
    assert plan["settings_may_persist_in_flash"] is True and plan["automatic_restore"] is False
    assert plan["rgb_readback_available"] is False and plan["adapter_enabled"] is False
    discover.assert_not_called()


@pytest.mark.parametrize("action", [0x18, 2, 0xF0, b"arbitrary", True])
def test_arbitrary_packets_report_ids_and_finish_are_unavailable(action):
    with pytest.raises(ValueError):
        probe.feature_payload(action)


def test_exact_payloads_have_static_blue_and_one_save_variant_only():
    start, mode, data, save = [probe.feature_payload(action) for action in probe.FixedFeature]
    assert all(len(payload) == 64 for payload in (start, mode, data, save))
    assert start[:3] == bytes((4, 0x18, 0)) and start[8] == 1
    assert mode[:3] == bytes((4, 0x13, 0)) and mode[8] == 1
    assert data[:4] == bytes((1, 0x40, 0x80, 0xFF))
    assert data[8:12] == bytes((0, 3, 0, 0)) and data[14:16] == bytes((0x55, 0xAA))
    assert save == bytes((4, 2)) + bytes(62)


def test_acknowledged_sequence_never_claims_rgb_readback_or_telemetry(monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", Mock())
    transport = FakeFeatures()
    result = probe.observe(transport)
    assert transport.sent == [probe.feature_payload(action) for action in probe.FixedFeature]
    assert transport.reads == 4
    assert result["status"] == "lighting_sequence_acknowledged_visual_check_required"
    assert result["actual_rgb"] is result["battery_percent"] is result["firmware_version"] is None
    assert result["persistence_verified"] is False and result["device_model_verified"] is False
    assert "private" not in json.dumps(result) and "serial" not in json.dumps(result)


@pytest.mark.parametrize(("replies", "outputs"), [
    ([b""], 0), ([bytes(64), bytes(64)], 1),
    ([bytes(64), ack(0x18), ack(2)], 2),
    ([bytes(64), ack(0x18), ack(0x13), bytes(64)], 4),
])
def test_first_bad_reply_stops_without_retry_restore_or_fallback(monkeypatch, replies, outputs):
    monkeypatch.setattr(probe.time, "sleep", Mock())
    transport = FakeFeatures(replies)
    with pytest.raises((probe.ProbeBlocked, probe.InvalidControlAcknowledgement)):
        probe.observe(transport)
    assert len(transport.sent) == outputs


@pytest.fixture
def fake_transport(monkeypatch):
    target = SimpleNamespace(verify_cached_identity=Mock())
    monkeypatch.setattr(probe, "check_competitors", Mock())
    ioctl = Mock(return_value=65)
    monkeypatch.setattr(probe.fcntl, "ioctl", ioctl)
    return probe.HidrawFeatures(target, 99, frozenset({42})), ioctl


def test_set_ioctls_always_prefix_zero_and_have_fixed_order_and_budget(fake_transport):
    transport, ioctl = fake_transport
    with pytest.raises(probe.ProbeBlocked):
        transport.send_feature(probe.FixedFeature.SAVE)
    ioctl.assert_not_called()
    for action in probe.FixedFeature:
        transport.send_feature(action)
    assert [call.args for call in ioctl.call_args_list] == [
        (99, probe.SET_FEATURE_65, bytearray(b"\0" + probe.feature_payload(action)), True) for action in probe.FixedFeature
    ]
    with pytest.raises(probe.ProbeBlocked):
        transport.send_feature(probe.FixedFeature.START)
    assert ioctl.call_count == 4


@pytest.mark.parametrize("count", [64, 65])
def test_get_accepts_only_complete_descriptor_specific_framing(fake_transport, count):
    transport, ioctl = fake_transport
    def read(descriptor, command, buffer, mutate):
        assert descriptor == 99 and command == probe.GET_FEATURE_65 and buffer[0] == 0 and len(buffer) == 65
        payload = ack(0x18)
        buffer[:] = (b"\0" + payload) if count == 65 else (payload + b"\0")
        return count
    ioctl.side_effect = read
    for _ in range(4):
        assert transport.get_feature() == ack(0x18)
    assert transport.diagnostics()["last_known_ack_command"] == 0x18
    assert transport.diagnostics()["last_known_ack_success"] is True
    with pytest.raises(probe.ProbeBlocked):
        transport.get_feature()
    assert ioctl.call_count == 4


@pytest.mark.parametrize("count", [0, 1, 63, 66])
def test_short_feature_replies_are_never_padded_or_retried(fake_transport, count):
    transport, ioctl = fake_transport
    ioctl.return_value = count
    with pytest.raises(probe.ProbeBlocked):
        transport.get_feature()
    ioctl.assert_called_once()


def test_partial_set_is_not_retried(fake_transport):
    transport, ioctl = fake_transport
    ioctl.return_value = 1
    with pytest.raises(probe.ProbeBlocked):
        transport.send_feature(probe.FixedFeature.START)
    assert transport.set_attempts == 1 and transport.set_completed == 0
    ioctl.assert_called_once()


def test_open_has_no_implicit_output_and_always_closes(monkeypatch):
    info = SimpleNamespace(st_mode=stat.S_IFCHR | 0o600, st_rdev=42)
    target = SimpleNamespace(node=Mock(lstat=Mock(return_value=info)), verify_cached_identity=Mock())
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(probe, "DeviceOwnership", lambda: SimpleNamespace(claim=lambda device: nullcontext()))
    monkeypatch.setattr(probe, "device_numbers", lambda target: frozenset({42}))
    monkeypatch.setattr(probe, "check_competitors", Mock())
    monkeypatch.setattr(probe.os, "open", Mock(return_value=99))
    monkeypatch.setattr(probe.os, "fstat", Mock(return_value=info))
    close, ioctl = Mock(), Mock(side_effect=AssertionError("Open/close must not send anything"))
    monkeypatch.setattr(probe.os, "close", close)
    monkeypatch.setattr(probe.fcntl, "ioctl", ioctl)
    with pytest.raises(RuntimeError):
        with probe.open_features(target, vendor_tools_closed=True):
            raise RuntimeError("Fake interrupted operation")
    close.assert_called_once_with(99)
    ioctl.assert_not_called()


def test_selector_requires_wired_interface_three_and_exact_cached_descriptor(monkeypatch, tmp_path):
    usb = tmp_path / "usb"
    interface = usb / "interface"
    hid = interface / "hid"
    hid.mkdir(parents=True)
    for name, value in {"idVendor": "0c45", "idProduct": "8009", "busnum": "1", "devnum": "2"}.items():
        (usb / name).write_text(value)
    (interface / "bInterfaceNumber").write_text("03")
    (hid / "uevent").write_text("HID_ID=0003:00000C45:00008009")
    (hid / "report_descriptor").write_bytes(b"fake FF13 descriptor")
    monkeypatch.setattr(probe, "DESCRIPTOR_SHA256", hashlib.sha256(b"fake FF13 descriptor").hexdigest())
    root = tmp_path / "class"
    (root / "hidraw7").mkdir(parents=True)
    (root / "hidraw7" / "device").symlink_to(hid, target_is_directory=True)
    target = probe.discover_target(root, tmp_path / "dev")
    assert target.node.name == "hidraw7" and str(tmp_path) not in repr(target)
    (hid / "report_descriptor").write_bytes(b"changed")
    with pytest.raises(probe.ProbeBlocked):
        target.verify_cached_identity()
    (hid / "uevent").write_text("HID_ID=0003:00000C45:0000FDFD")
    with pytest.raises(probe.ProbeBlocked):
        probe.discover_target(root, tmp_path / "dev")


def test_execute_requires_operator_confirmation_and_redacts_errors(monkeypatch, capsys):
    discover = Mock(side_effect=PermissionError("/private/serial"))
    monkeypatch.setattr(probe, "discover_target", discover)
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    assert probe.main(["--execute"]) == 2
    discover.assert_not_called()
    assert probe.main(["--execute", "--vendor-tools-closed"]) == 2
    assert "private" not in capsys.readouterr().out


def test_control_check_only_receives_one_feature_and_never_sends_or_infers_values():
    transport = FakeFeatures()
    result = probe.observe_control(transport)
    assert transport.reads == 1 and transport.sent == []
    assert result["status"] == "control_report_received"
    assert result["actual_rgb"] is result["battery_percent"] is result["firmware_version"] is None


def test_read_control_flag_cannot_be_combined_with_write_execution(monkeypatch):
    monkeypatch.setattr(probe, "discover_target", Mock(side_effect=AssertionError("No device IO")))
    with pytest.raises(SystemExit):
        probe.main(["--read-control", "--execute", "--vendor-tools-closed"])


def test_application_settings_require_both_consents_before_target_discovery(monkeypatch, capsys):
    discover = Mock(side_effect=AssertionError("No IO before consent/validation"))
    monkeypatch.setattr(probe, "discover_target", discover)
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1000)
    args = ["--apply-rgb", "--color", "#4080ff", "--brightness-percent", "60"]
    assert probe.main(args) == 2
    assert probe.main(args + ["--vendor-tools-closed"]) == 2
    bad = ["--apply-rgb", "--color", "#4080ff", "--brightness-percent", "50", "--vendor-tools-closed", "--allow-device-memory-writes"]
    assert probe.main(bad) == 2
    discover.assert_not_called()


def test_parameterized_static_data_preserves_the_fixed_sequence_and_no_rgb_readback(monkeypatch):
    target = SimpleNamespace(verify_cached_identity=Mock())
    monkeypatch.setattr(probe, "check_competitors", Mock())
    monkeypatch.setattr(probe.time, "sleep", Mock())
    responses = iter([bytes(64), ack(0x18), ack(0x13), ack(2)])
    outputs = []
    def ioctl(descriptor, command, buffer, mutate):
        assert descriptor == 99 and len(buffer) == 65 and mutate is True
        if command == probe.SET_FEATURE_65:
            assert buffer[0] == 0
            outputs.append(bytes(buffer[1:]))
            return 65
        assert command == probe.GET_FEATURE_65 and buffer[0] == 0
        buffer[:] = b"\0" + next(responses)
        return 65
    monkeypatch.setattr(probe.fcntl, "ioctl", ioctl)
    transport = probe.HidrawFeatures(target, 99, frozenset({42}), static_color="#123456", brightness_percent=40)
    result = probe.observe(transport, color="#123456", brightness_percent=40)
    assert len(outputs) == 4 and outputs[2][:4] == bytes.fromhex("01 12 34 56")
    assert outputs[2][9] == 2
    assert outputs[0] == probe.feature_payload(probe.FixedFeature.START)
    assert outputs[1] == probe.feature_payload(probe.FixedFeature.MODE_CONFIG)
    assert outputs[3] == probe.feature_payload(probe.FixedFeature.SAVE)
    assert result["requested"] == {"mode": "static", "color": "#123456", "brightness_level": 2}
    assert result["actual_rgb"] is None and result["persistence_verified"] is False
    assert transport.diagnostics()["feature_sets_completed"] == transport.diagnostics()["feature_gets_attempted"] == 4

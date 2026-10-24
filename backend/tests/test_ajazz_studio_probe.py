"""Offline source packets and fake transports; never access real HID."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from pcc.diagnostics import ajazz_studio_probe as probe
from pcc.drivers.protocols.ajazz_rgb import static_rgb_payload
from pcc.drivers.protocols.ajazz_studio import Command, StudioLighting, clock_payload, control_plan, lighting_payload, parse_ack, screen_test_payload, standby_payload


def test_static_plan_retains_the_exact_previously_verified_data_frame():
    settings = StudioLighting(effect='static', color='#4080ff', brightness=60, speed=0, direction='left', rainbow=False)
    assert lighting_payload(settings) == static_rgb_payload('#4080ff', 60)
    data = lighting_payload(settings.model_copy(update={'effect': 'breathe', 'speed': 3, 'direction': 'right', 'rainbow': True}))
    assert data[:4] == bytes.fromhex('07 40 80 ff') and data[8:12] == bytes((1,3,3,3))


@pytest.mark.parametrize('change', [{'effect': 'raw'}, {'brightness': 50}, {'speed': True}, {'speed': 6}, {'color': 'blue'}, {'direction': 3}, {'rainbow': 1}])
def test_invalid_source_settings_are_rejected(change):
    desired = {'effect': 'static', 'color': '#4080ff', 'brightness': 60, 'speed': 0, 'direction': 'left', 'rainbow': False}
    with pytest.raises(ValidationError):
        StudioLighting(**(desired | change))


def test_clock_standby_and_screen_patterns_are_bounded_and_offline():
    date = datetime(2026, 10, 24, 16, 32, 4, tzinfo=timezone.utc)
    data = clock_payload(date)
    assert data[:11] == bytes((0,1,90,26,10,24,16,32,4,0,4)) and data[-2:] == bytes.fromhex('aa55')
    with pytest.raises(ValueError): clock_payload(date.replace(tzinfo=None))
    with pytest.raises(ValueError): clock_payload(date.replace(year=2100))
    for level, minutes in enumerate((0,1,5,30)):
        assert standby_payload(minutes)[8] == level
    for bad in (True, 2, 10, -1):
        with pytest.raises(ValueError): standby_payload(bad)
    screen = screen_test_payload()
    assert len(screen) == 9 * 4096 and screen[:2] == b'\x01\x00'
    assert screen[256:258] == b'\x1f\x44' and screen[256 + 16 * 2:258 + 16 * 2] == b'\xff\xff'
    assert screen[256 + 32768:] == b'\xff' * (9 * 4096 - 256 - 32768)


@pytest.mark.parametrize('operation', ['lighting', 'clock', 'standby', 'screen'])
def test_plan_modes_have_no_device_discovery_or_io(monkeypatch, capsys, operation):
    discover = Mock(side_effect=AssertionError('Plan mode must not inspect hardware'))
    monkeypatch.setattr(probe.rgb, 'discover_target', discover)
    assert probe.main(['--operation', operation]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['device_io'] is False and result['retries'] == 0
    assert result['device_memory_write_required'] is True and result['actual_state_readback_available'] is False
    assert result['maximum_feature_sets'] in (3,4)
    discover.assert_not_called()


@pytest.mark.parametrize('operation', ['lighting', 'clock', 'standby'])
def test_full_control_sequence_has_matching_acks_and_no_invented_readback(monkeypatch, operation):
    operation_plan = probe.experiment(operation)
    replies = iter([bytes(64)] + [bytes((4,*step.acknowledgement.value,1)) + bytes(60) for step in operation_plan.steps if step.acknowledgement])
    transport = SimpleNamespace(get_feature=Mock(side_effect=lambda: next(replies)), send_step=Mock())
    monkeypatch.setattr(probe.time, 'sleep', Mock())
    result = probe.observe(transport, operation_plan)
    assert result['actual_settings'] is None and result['persistence_verified'] is False
    assert transport.get_feature.call_count == 4
    assert [call.args for call in transport.send_step.call_args_list] == [(0,),(1,),(2,),(3,)]


def test_bad_first_ack_stops_before_config_data_and_save(monkeypatch):
    transport = SimpleNamespace(get_feature=Mock(return_value=bytes(64)), send_step=Mock())
    monkeypatch.setattr(probe.time, 'sleep', Mock())
    with pytest.raises(ValueError): probe.observe(transport, probe.experiment('clock'))
    transport.send_step.assert_called_once_with(0)
    with pytest.raises(ValueError): parse_ack(bytes(64), Command.CLOCK)


def test_consent_precedes_discovery(monkeypatch, capsys):
    discover = Mock(side_effect=AssertionError('No IO'))
    monkeypatch.setattr(probe.rgb, 'discover_target', discover)
    monkeypatch.setattr(probe.os, 'geteuid', lambda: 1000)
    for flags in ([], ['--vendor-tools-closed']):
        assert probe.main(['--operation', 'lighting', '--execute', *flags]) == 2
    assert probe.main(['--operation', 'screen', '--execute', '--vendor-tools-closed']) == 2
    discover.assert_not_called()
    assert 'private' not in capsys.readouterr().out


def test_transport_enforces_plan_order_zero_report_id_and_four_sets(monkeypatch):
    base = SimpleNamespace(target=SimpleNamespace(verify_cached_identity=Mock()), descriptor=99, numbers=frozenset({42}))
    monkeypatch.setattr(probe.rgb, 'check_competitors', Mock())
    ioctl = Mock(return_value=65); monkeypatch.setattr(probe.rgb.fcntl, 'ioctl', ioctl)
    plan = probe.experiment('standby'); transport = probe.StudioFeatures(base, plan)
    with pytest.raises(probe.rgb.ProbeBlocked): transport.send_step(1)
    for index, step in enumerate(plan.steps):
        transport.send_step(index)
        assert ioctl.call_args.args == (99, probe.rgb.SET_FEATURE_65, bytearray(b'\0'+step.payload), True)
    with pytest.raises(probe.rgb.ProbeBlocked): transport.send_step(4)
    assert ioctl.call_count == 4

from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from pcc.diagnostics import ajazz_screen_probe as probe
from pcc.drivers.protocols.ajazz_studio import Command


def test_fixed_transfer_has_nine_chunks_and_no_fabricated_display_readback(monkeypatch):
    replies = iter([bytes(64)] + [bytes((4,*command.value,1))+bytes(60) for command in (Command.START,Command.IMAGE,Command.SAVE)])
    transport = SimpleNamespace(get_feature=Mock(side_effect=lambda: next(replies)), set_control=Mock(), send_chunk=Mock())
    monkeypatch.setattr(probe.time, 'sleep', Mock())
    result = probe.observe_screen(transport)
    assert transport.get_feature.call_count == 4
    assert [call.args for call in transport.send_chunk.call_args_list] == [(i,) for i in range(9)]
    assert [call.args for call in transport.set_control.call_args_list] == [(0,),(1,),(2,)]
    assert result['actual_settings'] is None and result['persistence_verified'] is False
    assert result['data_receipt_semantics_verified'] is False


@pytest.fixture
def transport(monkeypatch):
    target = SimpleNamespace(verify_cached_identity=Mock())
    control = SimpleNamespace(target=target, descriptor=99, get_attempts=0)
    result = probe.ScreenHidraw(control, target, 100, frozenset({1,2}))
    monkeypatch.setattr(probe.rgb, 'check_competitors', Mock())
    monkeypatch.setattr(probe.rgb.fcntl, 'ioctl', Mock(return_value=65))
    monkeypatch.setattr(probe.os, 'write', Mock(return_value=4097))
    monkeypatch.setattr(probe.os, 'read', Mock(return_value=bytes(64)))
    monkeypatch.setattr(probe.select, 'select', Mock(return_value=([100],[],[])))
    return result


def test_data_output_uses_zero_prefix_and_exact_4096_byte_chunks(transport):
    with pytest.raises(probe.rgb.ProbeBlocked): transport.send_chunk(0)
    transport.set_control(0); transport.set_control(1)
    with pytest.raises(probe.rgb.ProbeBlocked): transport.set_control(2)
    for index in range(9): transport.send_chunk(index)
    assert probe.os.write.call_count == 9
    assert all(len(call.args[1]) == 4097 and call.args[1][0] == 0 for call in probe.os.write.call_args_list)
    transport.set_control(2)
    assert transport.receipts == 9
    with pytest.raises(probe.rgb.ProbeBlocked): transport.send_chunk(9)
    with pytest.raises(probe.rgb.ProbeBlocked): transport.set_control(3)


@pytest.mark.parametrize('failure', ['partial', 'timeout', 'short_reply'])
def test_data_failure_stops_before_save_without_retry(transport, monkeypatch, failure):
    transport.set_control(0); transport.set_control(1)
    if failure == 'partial': probe.os.write.return_value = 2
    elif failure == 'timeout': probe.select.select.return_value = ([],[],[])
    else: probe.os.read.return_value = b'bad'
    with pytest.raises(probe.rgb.ProbeBlocked): transport.send_chunk(0)
    assert probe.os.write.call_count == 1
    with pytest.raises(probe.rgb.ProbeBlocked): transport.set_control(2)
    assert probe.rgb.fcntl.ioctl.call_count == 2


def test_bad_image_config_ack_prevents_all_data_outputs(monkeypatch):
    replies = iter([bytes(64), bytes((4,24,0,1))+bytes(60), bytes(64)])
    transport = SimpleNamespace(get_feature=Mock(side_effect=lambda: next(replies)), set_control=Mock(), send_chunk=Mock())
    monkeypatch.setattr(probe.time, 'sleep', Mock())
    with pytest.raises(ValueError): probe.observe_screen(transport)
    transport.send_chunk.assert_not_called()
    assert transport.set_control.call_count == 2

"""Application-child stdin admission tested without launching a child or opening HID."""
import base64
import io
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from pcc.diagnostics import ajazz_screen_apply as screen
from pcc.diagnostics import ajazz_screen_probe
from pcc.diagnostics import ajazz_studio_probe as control

CONSENT=['--vendor-tools-closed','--allow-device-memory-writes']


def test_screen_plan_and_rejected_input_never_open_hardware(monkeypatch,capsys):
    opening=Mock(side_effect=AssertionError('No hardware IO before complete admission'))
    monkeypatch.setattr(screen,'open_screen',opening)
    monkeypatch.setattr(screen.os,'geteuid',lambda:1000)
    assert screen.main([])==0
    assert screen.main(['--apply'])==2
    monkeypatch.setattr(screen.sys,'stdin',io.StringIO('{"frames":[],"packet":"private/path"}'))
    assert screen.main(['--apply',*CONSENT])==2
    opening.assert_not_called()
    assert 'private' not in capsys.readouterr().out


def test_multiframe_application_input_constructs_its_own_bounded_transfer(monkeypatch,capsys):
    frame={'rgb565_base64':base64.b64encode(bytes(32768)).decode(),'delay_ms':100}
    monkeypatch.setattr(screen.sys,'stdin',io.StringIO(json.dumps({'frames':[frame,frame]})))
    monkeypatch.setattr(screen.os,'geteuid',lambda:1000)
    monkeypatch.setattr(screen,'deadline',lambda:nullcontext())
    monkeypatch.setattr(ajazz_screen_probe.time,'sleep',Mock())
    replies=iter([bytes(64)]+[bytes((4,cmd,sub,1))+bytes(60) for cmd,sub in ((24,0),(114,3),(2,0))])
    transport=SimpleNamespace(get_feature=Mock(side_effect=lambda:next(replies)),set_control=Mock(),send_chunk=Mock(),diagnostics=lambda:{'fake':True})
    opening=Mock(return_value=nullcontext(transport));monkeypatch.setattr(screen,'open_screen',opening)
    assert screen.main(['--apply',*CONSENT])==0
    result=json.loads(capsys.readouterr().out)
    assert result['requested']['frame_count']==2
    payload=opening.call_args.args[0]
    assert len(payload)==17*4096 and payload[:3]==bytes((2,50,50))
    assert transport.send_chunk.call_count==17 and transport.get_feature.call_count==4


def test_control_application_rejects_operation_mismatch_and_arbitrary_fields(monkeypatch,capsys):
    discover=Mock(side_effect=AssertionError('No IO'))
    monkeypatch.setattr(control.rgb,'discover_target',discover)
    monkeypatch.setattr(control.os,'geteuid',lambda:1000)
    for content in ('{"operation":"clock","local_time":"2026-10-24T14:00:00+01:00"}',
                    '{"operation":"standby","minutes":5,"packet":"private/path"}'):
        monkeypatch.setattr(control.sys,'stdin',io.StringIO(content))
        assert control.main(['--operation','standby','--apply',*CONSENT])==2
    discover.assert_not_called()
    assert 'private' not in capsys.readouterr().out

import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import TypeAdapter

from pcc.diagnostics import pulsar_performance_apply as cli
from pcc.drivers.protocols.pulsar_performance import Register,action_packets,pair
from pcc.drivers.protocols.pulsar_readonly import ReplyTimeout
from pcc.drivers.pulsar_performance_transaction import apply_one
from pcc.performance_models import PerformanceAction,PerformanceApplyRequest,PerformanceCapabilities,ParameterCapability
from test_pulsar_performance_probe import FakePerformance


class FakeWriter(FakePerformance):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.writes=[]
        self.ignore=False
        self.unrequested=False
        self.fail=False

    def write_action(self,action,*,rotation_enabled):
        for packet in action_packets(action,rotation_enabled=rotation_enabled):
            self.writes.append(packet)
            if self.fail:
                raise ReplyTimeout()
            if not self.ignore:
                address=int.from_bytes(packet[3:5],'big')
                register=next(r for r in Register if r.value[0]==address)
                self.records[register]=packet[6:6+packet[5]]
        if self.unrequested:
            self.records[Register.LOD]=pair(2)


INTENTS=[{'operation':'stage_dpi','stage_index':0,'dpi':1200},
         {'operation':'active_stage','stage_index':1},{'operation':'polling_rate','hz':8000},
         {'operation':'lod','millimetres':2.0},{'operation':'debounce','milliseconds':8},
         *[{'operation':name,'enabled':True} for name in ['motion_sync','angle_snap','ripple_control','turbo']],
         {'operation':'rotation','degrees':-10}]


def request_and_caps(intent):
    request=PerformanceApplyRequest(action=TypeAdapter(PerformanceAction).validate_python(intent),
                                     vendor_tools_closed=True,allow_device_memory_writes=True,
                                     expected_profile_index=0,expected_active_stage_index=2)
    value=next(v for k,v in intent.items() if k not in {'operation','stage_index'}) if intent['operation']!='active_stage' else intent['stage_index']
    caps=PerformanceCapabilities(snapshot_read=True,parameters={request.action.operation:ParameterCapability(read=True,write=True,values=[value])})
    return request,caps


@pytest.mark.parametrize('intent',INTENTS)
def test_one_change_verifies_all_other_raw_records_and_current_profile(intent):
    request,caps=request_and_caps(intent)
    fake=FakeWriter()
    result=apply_one(fake,request,caps)
    assert len(fake.calls)==76
    assert len(fake.writes)==(2 if intent['operation']=='rotation' else 1)
    assert result.active_profile_index==0 and result.stage_count==5
    if intent['operation']=='rotation':
        assert result.sensor.rotation==-10 and result.sensor.rotation_enabled is True
    assert all(p[1]==7 and sum(p)&255==0x55 for p in fake.writes)


@pytest.mark.parametrize('flag', ['ignore','unrequested','fail'])
def test_uncertain_write_or_changed_other_settings_stop_without_restore(flag):
    request,caps=request_and_caps(INTENTS[0])
    fake=FakeWriter();setattr(fake,flag,True)
    with pytest.raises((ValueError,ReplyTimeout)):
        apply_one(fake,request,caps)
    assert len(fake.writes)==1
    assert len(fake.calls)==(38 if flag=='fail' else 76)


@pytest.mark.parametrize('patch',[{'vendor_tools_closed':False},{'allow_device_memory_writes':False},
                                {'expected_profile_index':1},{'expected_active_stage_index':1}])
def test_consent_and_context_checks_precede_settings_output(patch):
    request,caps=request_and_caps(INTENTS[0])
    fake=FakeWriter()
    with pytest.raises(ValueError):
        apply_one(fake,request.model_copy(update=patch),caps)
    assert not fake.writes


def test_unknown_rotation_support_and_unconfigured_stage_are_not_written():
    request,caps=request_and_caps(INTENTS[-1])
    fake=FakeWriter()
    fake.records[Register.ROTATION]=fake.records[Register.ROTATION_STATE]=b'\xff\xff'
    with pytest.raises(ValueError,match='support'):
        apply_one(fake,request,caps)
    assert not fake.writes
    request,caps=request_and_caps({'operation':'stage_dpi','stage_index':5,'dpi':800})
    with pytest.raises(ValueError,match='exist'):
        apply_one(fake,request,caps)
    assert not fake.writes


def test_evidence_gate_rejects_before_reads_and_cli_never_opens_unvalidated_writer(monkeypatch,capsys):
    request,_caps=request_and_caps(INTENTS[0])
    fake=FakeWriter()
    with pytest.raises(ValueError,match='validated'):
        apply_one(fake,request,PerformanceCapabilities())
    assert not fake.calls
    discover=Mock(side_effect=AssertionError('Unvalidated writer must not open'))
    monkeypatch.setattr(cli,'discover_target',discover)
    monkeypatch.setattr(cli.os,'geteuid',lambda:1000)
    monkeypatch.setattr(cli.sys,'stdin',io.StringIO(request.model_dump_json()))
    assert cli.main(['--apply'])==2
    assert json.loads(capsys.readouterr().out)['settings_may_have_changed'] is False
    discover.assert_not_called()


def test_default_apply_plan_is_inert_and_has_no_enabled_new_operations(capsys):
    assert cli.main([])==0
    data=json.loads(capsys.readouterr().out)
    assert data['device_io'] is False and data['enabled_operations']==[]
    assert data['maximum_output_reports']==82 and data['maximum_settings_write_reports']==2


def test_live_transport_counts_uncertain_output_and_cannot_replay(monkeypatch):
    write=Mock(return_value=17)
    monkeypatch.setattr(cli.os,'write',write)
    monkeypatch.setattr(cli,'check_competitors',Mock())
    monkeypatch.setattr(cli,'receive_write_ack',Mock(side_effect=ReplyTimeout()))
    opened=SimpleNamespace(target=SimpleNamespace(verify_cached_identity=Mock()),numbers=frozenset(),descriptor=99)
    transport=cli.PerformanceApplyHidraw(opened)
    request,_caps=request_and_caps(INTENTS[-1])
    with pytest.raises(ReplyTimeout):transport.write_action(request.action,rotation_enabled=False)
    assert transport.sent==transport.settings_writes==1
    with pytest.raises(cli.ProbeBlocked):transport.write_action(request.action,rotation_enabled=False)
    write.assert_called_once()

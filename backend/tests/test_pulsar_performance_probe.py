import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pcc.diagnostics import pulsar_performance_probe as probe
from pcc.drivers.protocols.pulsar_performance import DPI_REGISTERS, Register, dpi_record, pair
from pcc.drivers.protocols.pulsar_readonly import InvalidReply, Reply, ReplyTimeout


class FakePerformance:
    def __init__(self, count=5):
        self.count = count
        self.calls = []
        self.profile = 0
        self.records = {r:pair(0) for r in Register if r.value[1] == 2}
        self.records.update({Register.STAGE_COUNT:pair(count), Register.ACTIVE_STAGE:pair(2),
                             Register.POLLING:pair(1), Register.LOD:pair(1), Register.DEBOUNCE:pair(5)})
        self.records.update({r:dpi_record(value) for r,value in zip(DPI_REGISTERS, [400,800,1200,1600,3200,6400])})

    def exchange(self, query):
        self.calls.append(query)
        if query is probe.Query.IDENTITY:
            return Reply(1, bytes.fromhex('00 00 00 00 57 27 05 00'))
        if query is probe.Query.FIRMWARE:
            return Reply(18, b'\x03\x03')
        if query is probe.Query.PROFILE:
            return Reply(14, bytes((self.profile,)))
        return Reply(8, self.records[query])


def test_plan_is_inert_and_discloses_exact_read_budget(monkeypatch,capsys):
    discover = Mock(side_effect=AssertionError('No hardware in plan'))
    monkeypatch.setattr(probe,'discover_target',discover)
    assert probe.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['maximum_output_reports'] == 40 and result['output_reports_for_five_stages'] == 38
    assert result['maximum_settings_write_reports'] == result['retries'] == 0
    assert result['device_io'] is False
    discover.assert_not_called()


@pytest.mark.parametrize('count,expected', [(3,34),(5,38),(6,40)])
def test_reads_only_current_configured_stages_twice(count,expected):
    fake = FakePerformance(count)
    result = probe.observe(fake)
    assert len(fake.calls) == expected
    assert result.stage_count == count and len(result.stages) == count
    assert result.stages[2].x == result.stages[2].y == 1200
    assert result.sensor.debounce == 5 and result.sensor.motion_sync is False
    assert all(r not in fake.calls for r in DPI_REGISTERS[count:])
    assert all(probe.packet_for(q)[1] in {1,8,14,18} for q in fake.calls)


def test_a_profile_change_between_passes_invalidates_snapshot():
    fake = FakePerformance()
    exchange = fake.exchange
    def changed(query):
        if len(fake.calls) == 19:
            fake.profile = 1
        return exchange(query)
    fake.exchange = changed
    with pytest.raises(probe.ProbeBlocked,match='changed'):
        probe.observe(fake)


@pytest.mark.parametrize('register,record', [(Register.STAGE_COUNT,pair(7)), (Register.ACTIVE_STAGE,pair(5)),
                                          (Register.POLLING,b'\0\0'), (Register.DPI_2,bytes(4))])
def test_invalid_bounds_or_checksums_do_not_become_defaults(register,record):
    fake = FakePerformance()
    fake.records[register] = record
    with pytest.raises((InvalidReply,probe.ProbeBlocked)):
        probe.observe(fake)


def test_unknown_and_asymmetric_values_are_retained_truthfully():
    fake = FakePerformance()
    fake.records[Register.DPI_0] = bytes.fromhex('4f 77 00 8f')
    fake.records[Register.ROTATION] = fake.records[Register.ROTATION_STATE] = b'\xff\xff'
    fake.records[Register.LOD] = pair(9)
    result = probe.observe(fake)
    assert (result.stages[0].x,result.stages[0].y) == (800,1200)
    assert result.sensor.rotation is None and result.sensor.lod is None


def test_unknown_firmware_aborts_early():
    fake = FakePerformance()
    exchange = fake.exchange
    fake.exchange = lambda q: Reply(18,b'\x03\x04') if q is probe.Query.FIRMWARE else exchange(q)
    with pytest.raises(probe.ProbeBlocked,match='firmware'):
        probe.observe(fake)
    assert fake.calls == [probe.Query.IDENTITY]


def test_transport_has_fixed_budget_and_does_not_retry_incomplete_writes(monkeypatch):
    opened = SimpleNamespace(target=SimpleNamespace(verify_cached_identity=Mock()), numbers=frozenset(), descriptor=99)
    write = Mock(return_value=0)
    monkeypatch.setattr(probe.os,'write',write)
    monkeypatch.setattr(probe,'check_competitors',Mock())
    transport = probe.PerformanceHidraw(opened)
    with pytest.raises(probe.ProbeBlocked,match='Incomplete'):
        transport.exchange(Register.LOD)
    write.assert_called_once()
    transport.sent = 40
    with pytest.raises(probe.ProbeBlocked,match='budget'):
        transport.exchange(Register.LOD)
    write.assert_called_once()


def test_timeout_stops_without_another_query():
    fake = FakePerformance()
    fake.exchange = Mock(side_effect=ReplyTimeout())
    with pytest.raises(ReplyTimeout):
        probe.observe(fake)
    fake.exchange.assert_called_once_with(probe.Query.IDENTITY)


def test_execute_requires_operator_and_normal_user(monkeypatch,capsys):
    discover = Mock(side_effect=AssertionError('No open'))
    monkeypatch.setattr(probe,'discover_target',discover)
    assert probe.main(['--execute']) == 2
    monkeypatch.setattr(probe.os,'geteuid',lambda:0)
    assert probe.main(['--execute','--vendor-tools-closed']) == 2
    discover.assert_not_called()

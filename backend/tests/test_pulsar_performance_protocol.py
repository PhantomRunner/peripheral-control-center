import pytest
from pydantic import TypeAdapter, ValidationError

from pcc.drivers.protocols.pulsar_performance import (Register, decode_sensor, dpi_axes, dpi_record,
                                                    pair, read_packet, write_packet, write_record)
from pcc.drivers.protocols.pulsar_readonly import InvalidReply
from pcc.performance_models import PerformanceAction, PerformanceApplyRequest

actions = TypeAdapter(PerformanceAction)


@pytest.mark.parametrize('dpi,hex_record', [
    (400,'27 27 00 07'), (800,'4f 4f 00 b7'), (1200,'77 77 00 67'),
    (3200,'3f 3f 44 93'), (12800,'37 37 22 c5'), (32000,'77 77 33 34'),
])
def test_source_samples_and_axes_round_trip(dpi, hex_record):
    assert dpi_record(dpi) == bytes.fromhex(hex_record)
    assert dpi_axes(dpi_record(dpi)) == (dpi, dpi)


@pytest.mark.parametrize('dpi', [True, 0, 9, 11, 10241, 10510, 25650, 32001])
def test_unrepresentable_dpi_is_rejected(dpi):
    with pytest.raises(ValueError):
        dpi_record(dpi)


def test_axes_are_not_silently_collapsed():
    assert dpi_axes(bytes.fromhex('4f 77 00 8f')) == (800, 1200)
    assert dpi_axes(bytes((0,0,0x11,0x44))) == (None, None)
    with pytest.raises(InvalidReply):
        dpi_axes(bytes(4))


@pytest.mark.parametrize('body,address,length', [
    ({'operation':'stage_dpi','stage_index':5,'dpi':1600},0x20,4),
    ({'operation':'active_stage','stage_index':1},4,2),
    ({'operation':'polling_rate','hz':8000},0,2),
    ({'operation':'lod','millimetres':0.7},10,2),
    ({'operation':'debounce','milliseconds':15},169,2),
    ({'operation':'motion_sync','enabled':True},171,2),
    ({'operation':'angle_snap','enabled':False},175,2),
    ({'operation':'ripple_control','enabled':True},177,2),
    ({'operation':'turbo','enabled':True},181,2),
    ({'operation':'rotation','degrees':-30},189,2),
])
def test_named_writes_have_finite_records(body,address,length):
    action = actions.validate_python(body)
    register, record = write_record(action)
    packet = write_packet(action)
    assert register.value == (address,length)
    assert len(packet) == 17 and packet[:2] == bytes((8,7))
    assert sum(packet) & 255 == sum(record) & 255 == 0x55
    assert packet[6:6+length] == record


@pytest.mark.parametrize('body', [
    {'operation':'raw','address':1,'value':0}, {'operation':'active_stage','stage_index':True},
    {'operation':'stage_dpi','stage_index':6,'dpi':800}, {'operation':'debounce','milliseconds':'5'},
    {'operation':'motion_sync','enabled':1}, {'operation':'rotation','degrees':31},
    {'operation':'lod','millimetres':3.0}, {'operation':'polling_rate','hz':999},
    {'operation':'turbo','enabled':True,'address':8},
])
def test_strict_actions_reject_coercion_and_raw_fields(body):
    with pytest.raises(ValidationError):
        actions.validate_python(body)


def test_read_queries_are_allowlisted_and_cannot_write():
    for register in Register:
        packet = read_packet(register)
        assert packet[1] == 8 and sum(packet) & 255 == 0x55
        assert packet[6:16] == bytes(10)
    for raw in [0, (0,2), b'arbitrary', True]:
        with pytest.raises(ValueError):
            read_packet(raw)
        with pytest.raises(ValueError):
            write_packet(raw)


def test_unknown_sensor_values_and_optional_rotation_are_unavailable():
    assert decode_sensor('lod', pair(3)) == 0.7
    assert decode_sensor('lod', pair(4)) is None
    assert decode_sensor('debounce', pair(16)) is None
    assert decode_sensor('motion_sync', pair(2)) is None
    assert decode_sensor('rotation', pair(226), pair(1)) == -30
    assert decode_sensor('rotation', b'\xff\xff', b'\xff\xff') is None
    with pytest.raises(InvalidReply):
        decode_sensor('turbo', bytes(2))


def test_apply_requires_context_and_defaults_to_no_consent():
    body = PerformanceApplyRequest(action=actions.validate_python({'operation':'debounce','milliseconds':5}),
                                   expected_profile_index=0, expected_active_stage_index=2)
    assert not body.vendor_tools_closed and not body.allow_device_memory_writes


def test_discovery_never_advertises_unvalidated_performance_operations():
    from pcc.drivers.pulsar import PulsarAdapter
    for presence in [set(), {'3710:5406'}]:
        caps = PulsarAdapter().get_summary(presence).performance_capabilities
        assert caps is not None and caps.snapshot_read is False
        assert all(not item.read and not item.write and not item.values for item in caps.parameters.values())

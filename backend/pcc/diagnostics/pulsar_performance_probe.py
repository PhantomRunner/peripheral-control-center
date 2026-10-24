"""Fixed current-profile performance read. Default prints a plan, never opens HID.

Execution requires separate approval of this exact read experiment. No settings,
profile selection, config-mode, scanning, retry or restoration commands exist here.
"""

import argparse
import json
import os
import signal
from contextlib import contextmanager
from enum import Enum

from pcc.diagnostics.pulsar_config_probe import ConfigQuery, query_packet as config_packet
from pcc.diagnostics.pulsar_probe import (DESCRIPTOR_SHA256, FixedQuery, HidrawProbe, ProbeBlocked,
                                         check_competitors, discover_target, open_probe,
                                         query_packet as telemetry_packet)
from pcc.drivers.protocols.pulsar_performance import (DPI_REGISTERS, SENSOR_REGISTERS, Register,
                                                     decode_sensor, dpi_axes, read_packet)
from pcc.drivers.protocols.pulsar_readonly import (ExpectedReply, InvalidReply, Reply, ReplyTimeout,
                                                 complemented_value, firmware_version, polling_rate, receive_reply)
from pcc.ownership import DeviceBusyError, OwnershipUnavailableError
from pcc.performance_models import DpiStage, PerformanceSnapshot, SensorSnapshot


class Query(Enum):
    IDENTITY = 1
    FIRMWARE = 18
    PROFILE = 14


def packet_for(query: Query | Register) -> bytes:
    if type(query) is Register:
        return read_packet(query)
    if query is Query.IDENTITY:
        return config_packet(ConfigQuery.IDENTITY)
    if query is Query.PROFILE:
        return config_packet(ConfigQuery.PROFILE)
    if query is Query.FIRMWARE:
        return telemetry_packet(FixedQuery.MOUSE_FIRMWARE)
    raise ValueError('Only named performance reads are allowed.')


def plan() -> dict:
    return {
        'mode': 'plan', 'device_io': False, 'usb_id': '3710:5406', 'interface': 1,
        'descriptor_sha256': DESCRIPTOR_SHA256,
        'expected_identity': {'cid': 87, 'mid': 39, 'type': 5}, 'firmware': '3.03',
        'sequence': ['identity', 'firmware', 'current_profile', 'stage_count', 'active_stage',
                     'polling', 'configured_dpi_stages_only', *SENSOR_REGISTERS, 'rotation_support_state'],
        'passes': 2, 'maximum_output_reports': 40, 'output_reports_for_five_stages': 38,
        'maximum_settings_write_reports': 0, 'retries': 0,
        'receive_timeout_seconds_per_query': 0.5, 'process_deadline_seconds': 24,
        'registers': [{'name': r.name.lower(), 'address': r.value[0], 'length': r.value[1]} for r in Register],
        'requires_separate_unvalidated_read_approval': True, 'requires_vendor_tools_closed': True,
        'adapter_activation': False,
    }


@contextmanager
def deadline():
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ProbeBlocked('Run this diagnostic in a standalone process.')
    def expired(_signum, _frame):
        raise ProbeBlocked('Performance read deadline reached.')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 24)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class PerformanceHidraw:
    def __init__(self, opened: HidrawProbe):
        self.opened = opened
        self.sent = 0
        self.last_query: str | None = None

    def exchange(self, query: Query | Register) -> Reply:
        packet = packet_for(query)
        if self.sent >= 40:
            raise ProbeBlocked('Performance read budget exhausted.')
        self.opened.target.verify_cached_identity()
        check_competitors(self.opened.numbers)
        self.last_query = query.name.lower()
        self.sent += 1
        if os.write(self.opened.descriptor, packet) != len(packet):
            raise ProbeBlocked('Incomplete query; no retry.')
        expected = ExpectedReply(8, *query.value) if type(query) is Register else ExpectedReply(query.value)
        return receive_reply(self.opened, expected, timeout_seconds=0.5, max_reports=32)


def _capture(transport) -> tuple[dict, dict[Register, bytes]]:
    identity = transport.exchange(Query.IDENTITY)
    if identity.command != 1 or len(identity.payload) < 7 or identity.payload[4:7] != bytes((87,39,5)):
        raise ProbeBlocked('Mouse identity is not PSSTX21.')
    firmware = firmware_version(transport.exchange(Query.FIRMWARE))
    if firmware != '3.03':
        raise ProbeBlocked('This experiment is limited to firmware 3.03.')
    reply = transport.exchange(Query.PROFILE)
    if reply.command != 14 or len(reply.payload) != 1 or reply.payload[0] > 3:
        raise InvalidReply('Current profile is unavailable.')
    profile = reply.payload[0]
    count = complemented_value(transport.exchange(Register.STAGE_COUNT))
    active = complemented_value(transport.exchange(Register.ACTIVE_STAGE))
    if not 1 <= count <= 6 or active >= count:
        raise InvalidReply('Inconsistent DPI stage bounds.')
    registers = (Register.POLLING, *DPI_REGISTERS[:count], *SENSOR_REGISTERS.values(), Register.ROTATION_STATE)
    records = {register: transport.exchange(register).payload for register in registers}
    return {'firmware': firmware, 'profile': profile, 'count': count, 'active': active}, records


def observe(transport) -> PerformanceSnapshot:
    context, records = _capture(transport)
    if _capture(transport) != (context, records):
        raise ProbeBlocked('Performance settings changed during the read; snapshot discarded.')
    stages = [DpiStage(index=index, x=axes[0], y=axes[1])
              for index, register in enumerate(DPI_REGISTERS[:context['count']])
              for axes in [dpi_axes(records[register])]]
    sensor = {name: decode_sensor(name, records[register], records[Register.ROTATION_STATE])
              for name, register in SENSOR_REGISTERS.items()}
    return PerformanceSnapshot(firmware_version=context['firmware'], active_profile_index=context['profile'],
                               stage_count=context['count'], active_stage_index=context['active'], stages=stages,
                               polling_rate_hz=polling_rate(Reply(8, records[Register.POLLING])),
                               sensor=SensorSnapshot(**sensor))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--vendor-tools-closed', action='store_true')
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(plan(), indent=2))
        return 0
    if not args.vendor_tools_closed or os.geteuid() == 0:
        print(json.dumps({'status':'blocked', 'detail':'Normal user and explicit operator tool-closure confirmation required.'}))
        return 2
    transport = None
    try:
        target = discover_target()
        with deadline(), open_probe(target, vendor_tools_closed=True) as opened:
            transport = PerformanceHidraw(opened)
            snapshot = observe(transport)
        print(json.dumps({'status':'performance_observed', 'snapshot':snapshot.model_dump(mode='json'),
                          'output_reports_sent':transport.sent, 'settings_write_reports':0,
                          'adapter_activation':False}))
        return 0
    except (ProbeBlocked, InvalidReply, ReplyTimeout, OSError, ValueError, DeviceBusyError, OwnershipUnavailableError):
        print(json.dumps({'status':'blocked', 'detail':'Performance read was not confirmed; no retry or settings write.',
                          'output_reports_attempted':transport.sent if transport else 0,
                          'last_query':transport.last_query if transport else None, 'settings_write_reports':0}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

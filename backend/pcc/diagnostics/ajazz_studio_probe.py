"""Separately approved fixed Studio validation; default only prints a plan.

No firmware, pairing, reset, arbitrary packet, alternate framing or retry.
SAVE may persist in device memory. Acknowledgement is not actual state readback.
"""
import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from pcc.diagnostics import ajazz_rgb_probe as rgb
from pcc.drivers.protocols.ajazz_studio import Command, ControlPlan, StudioLighting, control_plan, parse_ack, screen_config_payload, screen_test_payload
from pcc.ownership import DeviceBusyError, OwnershipUnavailableError


def experiment(operation: str) -> ControlPlan:
    if operation == 'lighting':
        return control_plan('lighting', StudioLighting(effect='breathe', color='#4080ff', brightness=60, speed=3, direction='left', rainbow=False))
    if operation == 'clock':
        return control_plan('clock', datetime.now(ZoneInfo('Europe/Dublin')).replace(microsecond=0))
    if operation == 'standby':
        return control_plan('standby', 5)
    raise ValueError('Unsupported fixed control experiment.')


def plan(operation: str) -> dict:
    base = {'operation': operation, 'mode': 'plan', 'device_io': False, 'usb_id': '0c45:8009',
            'control_descriptor_sha256': rgb.DESCRIPTOR_SHA256, 'requires_separate_approval': True,
            'device_memory_write_required': True, 'actual_state_readback_available': False,
            'retries': 0, 'automatic_restore': False, 'finish_command': False}
    if operation == 'screen':
        start = bytearray(rgb.feature_payload(rgb.FixedFeature.START)); start[8] = 0
        return {**base, 'requested': 'one static 128×128 blue/white checkerboard, replacing current TFT image',
                'data_interface': 2, 'data_descriptor_sha256': '949444322d886b5e812e965ab489434f765546581bfae8fb72df5185c0cb1169',
                'control_sets': [bytes(start).hex(' '), screen_config_payload().hex(' '), rgb.feature_payload(rgb.FixedFeature.SAVE).hex(' ')],
                'maximum_feature_sets': 3, 'maximum_feature_gets': 4, 'maximum_data_outputs': 9,
                'data_payload_bytes': 9 * 4096, 'data_payload_sha256': hashlib.sha256(screen_test_payload()).hexdigest(),
                'data_reply_deadline_seconds': .3, 'process_deadline_seconds': 8}
    operation_plan = experiment(operation)
    return {**base, 'requested': operation_plan.requested,
            'sets': [{'step': step.name, 'payload_hex': step.payload.hex(' ')} for step in operation_plan.steps],
            'maximum_feature_sets': 4, 'maximum_feature_gets': 4, 'maximum_data_outputs': 0, 'process_deadline_seconds': 8}


class Features(Protocol):
    def get_feature(self) -> bytes: ...
    def send_step(self, index: int) -> None: ...


class StudioFeatures(rgb.HidrawFeatures):
    def __init__(self, base: rgb.HidrawFeatures, operation_plan: ControlPlan):
        super().__init__(base.target, base.descriptor, base.numbers)
        self.operation_plan = operation_plan

    def send_step(self, index: int) -> None:
        if type(index) is not int or index != self.set_attempts or not 0 <= index < 4:
            raise rgb.ProbeBlocked('The fixed operation order/budget was exceeded.')
        step = self.operation_plan.steps[index]
        self.phase = step.name
        self._preflight()
        self.set_attempts += 1
        count = rgb.fcntl.ioctl(self.descriptor, rgb.SET_FEATURE_65, bytearray(b'\0' + step.payload), True)
        if count not in (64, 65):
            raise rgb.ProbeBlocked('Incomplete feature output; no retry.')
        self.set_completed += 1


def observe(transport: Features, operation_plan: ControlPlan) -> dict:
    if len(transport.get_feature()) != 64:
        raise rgb.ProbeBlocked('Incomplete initial feature reply.')
    for index, step in enumerate(operation_plan.steps):
        transport.send_step(index)
        time.sleep(.04)
        if step.acknowledgement is not None:
            parse_ack(transport.get_feature(), step.acknowledgement)
    return {'status': 'sequence_acknowledged_visual_check_required', 'operation': operation_plan.operation,
            'requested': operation_plan.requested, 'usb_id': '0c45:8009', 'actual_settings': None, 'persistence_verified': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', required=True, choices=('lighting', 'clock', 'standby', 'screen'))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--vendor-tools-closed', action='store_true')
    parser.add_argument('--allow-device-memory-writes', action='store_true')
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(plan(args.operation), indent=2)); return 0
    transport = None
    try:
        if os.geteuid() == 0 or not args.vendor_tools_closed or not args.allow_device_memory_writes:
            raise rgb.ProbeBlocked('Normal user and separate tool/memory consent are required.')
        if args.operation == 'screen':
            from pcc.diagnostics.ajazz_screen_probe import open_screen, observe_screen
            with rgb.process_deadline(), open_screen() as transport:
                result = observe_screen(transport)
                result['diagnostics'] = transport.diagnostics()
        else:
            operation_plan = experiment(args.operation)
            target = rgb.discover_target()
            with rgb.process_deadline(), rgb.open_features(target, vendor_tools_closed=True) as base:
                transport = StudioFeatures(base, operation_plan)
                result = observe(transport, operation_plan)
                result['diagnostics'] = transport.diagnostics()
        print(json.dumps(result)); return 0
    except (rgb.ProbeBlocked, OSError, ValueError, DeviceBusyError, OwnershipUnavailableError):
        print(json.dumps({'status': 'blocked', 'operation': args.operation,
                          'detail': 'Studio experiment was not confirmed. No retry, restore or fallback; settings may have changed.',
                          'diagnostics': transport.diagnostics() if transport is not None else None})); return 2


if __name__ == '__main__':
    raise SystemExit(main())

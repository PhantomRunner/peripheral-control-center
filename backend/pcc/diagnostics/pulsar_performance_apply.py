"""Finite semantic performance Apply. New hardware writes remain evidence-gated."""

import argparse
import json
import os
import sys

from pcc.diagnostics.pulsar_performance_probe import PerformanceHidraw, deadline
from pcc.diagnostics.pulsar_probe import ProbeBlocked, check_competitors, discover_target, open_probe
from pcc.drivers.protocols.pulsar_performance import action_packets
from pcc.drivers.protocols.pulsar_settings import receive_write_ack
from pcc.drivers.pulsar_performance_transaction import apply_one
from pcc.ownership import DeviceBusyError, OwnershipUnavailableError
from pcc.performance_models import PerformanceApplyRequest, PerformanceApplyResult
from pcc.performance_support import validate_action, validated_capabilities


class PerformanceApplyHidraw(PerformanceHidraw):
    def __init__(self, opened):
        super().__init__(opened, maximum_reports=82)
        self.settings_writes = 0
        self.used = False

    def write_action(self, action, *, rotation_enabled=None):
        packets = action_packets(action, rotation_enabled=rotation_enabled)
        if self.used or len(packets) > 2 or self.sent + len(packets) > 82:
            raise ProbeBlocked('Single-action write budget exhausted.')
        self.used = True
        for packet in packets:
            self.opened.target.verify_cached_identity()
            check_competitors(self.opened.numbers)
            self.sent += 1
            self.settings_writes += 1  # Count before output; never replay ambiguity.
            if os.write(self.opened.descriptor, packet) != len(packet):
                raise ProbeBlocked('Incomplete settings write; state may have changed.')
            receive_write_ack(self.opened)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps({'mode':'plan','device_io':False,'maximum_output_reports':82,
                          'maximum_settings_write_reports':2,'retries':0,'restoration':False,
                          'process_deadline_seconds':50,'enabled_operations':[
                              name for name,cap in validated_capabilities().parameters.items() if cap.write]}))
        return 0
    transport = None
    try:
        raw = sys.stdin.read(4097)
        if len(raw) > 4096 or os.geteuid() == 0:
            raise ValueError('Invalid input or privileged execution.')
        request = PerformanceApplyRequest.model_validate_json(raw)
        capabilities = validated_capabilities()
        validate_action(request.action,capabilities)
        if not request.vendor_tools_closed or not request.allow_device_memory_writes:
            raise ValueError('Both explicit consent flags are required.')
        target = discover_target()
        with deadline(50), open_probe(target,vendor_tools_closed=True) as opened:
            transport = PerformanceApplyHidraw(opened)
            actual = apply_one(transport,request,capabilities)
        result = PerformanceApplyResult(requested=request.action,actual=actual)
        print(json.dumps({'result':result.model_dump(mode='json'),'output_reports_sent':transport.sent,
                          'settings_write_reports':transport.settings_writes}))
        return 0
    except (ProbeBlocked, OSError, ValueError, TimeoutError, DeviceBusyError, OwnershipUnavailableError):
        print(json.dumps({'status':'blocked','detail':'Performance Apply was not confirmed. No retry or restoration.',
                          'settings_may_have_changed':bool(transport and transport.settings_writes),
                          'output_reports_attempted':transport.sent if transport else 0}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

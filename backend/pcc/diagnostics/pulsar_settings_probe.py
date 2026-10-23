"""Fixed settings-write experiment, requiring its own explicit authorization.

Default is plan-only. Settings writes may persist in onboard memory on this
firmware. This is NOT covered by read-query approval. No firmware, pairing,
reset, profile selection, config-mode command, scanner or live adapter exists.
Frame/encoding reference: MIT Nordic notes credited in pulsar_readonly.py.
"""

import argparse
import json
import os
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Protocol

from pcc.diagnostics.pulsar_config_probe import ConfigHidraw, ConfigQuery, observe as read_config
from pcc.diagnostics.pulsar_probe import (
    DESCRIPTOR_SHA256, HidrawProbe, ProbeBlocked, check_competitors, discover_target, open_probe,
)
from pcc.drivers.protocols.pulsar_readonly import InvalidReply, Reply, ReplyTimeout, ReportSource
from pcc.ownership import DeviceBusyError, OwnershipUnavailableError


class FixedWrite(Enum):
    TEST_DPI_800 = (0x0014, bytes.fromhex("4f 4f 00 b7"))
    TEST_POLLING_500 = (0x0000, bytes.fromhex("02 53"))
    RESTORE_DPI_1200 = (0x0014, bytes.fromhex("77 77 00 67"))
    RESTORE_POLLING_1000 = (0x0000, bytes.fromhex("01 54"))


def write_packet(action: FixedWrite) -> bytes:
    if type(action) is not FixedWrite:
        raise ValueError("Only four fixed experiment writes are supported.")
    address, payload = action.value
    packet = bytearray(17)
    packet[:2] = bytes((8, 7))
    packet[3:5] = address.to_bytes(2, "big")
    packet[5] = len(payload)
    packet[6:6 + len(payload)] = payload
    packet[16] = (0x55 - sum(packet[:16])) & 255
    return bytes(packet)


def plan() -> dict:
    return {
        "mode": "plan", "device_io": False, "usb_id": "3710:5406", "interface": 1,
        "descriptor_sha256": DESCRIPTOR_SHA256,
        "required_baseline": {"cid": 87, "mid": 39, "type": 5, "profile_index": 0,
                              "stage_count": 5, "active_stage_index": 2, "dpi": 1200, "polling_rate_hz": 1000},
        "test_settings": {"dpi": 800, "polling_rate_hz": 500},
        "restore_settings": {"dpi": 1200, "polling_rate_hz": 1000},
        "write_packets": [{"action": action.name.lower(), "packet_hex": write_packet(action).hex(" ")} for action in FixedWrite],
        "read_sequence": "The twelve fixed config-read queries before writes, after both test writes, and after both restore writes.",
        "maximum_output_reports": 40, "maximum_settings_write_reports": 4,
        "retries": 0, "process_deadline_seconds": 30,
        "settings_writes_may_persist": True, "firmware_operations": False,
        "restore_only_after_confirmed_test_snapshot": True,
        "requires_separate_settings_memory_write_approval": True,
        "requires_vendor_tools_closed": True, "settings_adapter_activation": False,
    }


def receive_write_ack(source: ReportSource) -> None:
    deadline = time.monotonic() + 0.5
    for _ in range(32):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            packet = source.read_report(remaining)
        except TimeoutError:
            break
        if (len(packet) == 17 and packet[:3] == bytes((8, 7, 0))
                and packet[5] <= 10 and sum(packet) & 255 == 0x55):
            return  # ACK only; applied values still require independent config reads.
    raise ReplyTimeout("Settings-write acknowledgement was not confirmed.")


class WriteTransport(Protocol):
    def exchange(self, query: ConfigQuery) -> Reply: ...
    def write_setting(self, action: FixedWrite) -> None: ...


def _expect_snapshot(snapshot: dict, dpi: int, hz: int) -> None:
    if (snapshot["identity"] != {"cid": 87, "mid": 39, "type": 5}
            or snapshot["active_profile_index"] != 0 or snapshot["stage_count"] != 5
            or snapshot["active_stage_index"] != 2
            or snapshot["observed"] != {"dpi_candidate": dpi, "stored_polling_rate_hz_candidate": hz}):
        raise ProbeBlocked("Settings/profile/stage did not match this fixed experiment; no further write is allowed.")


def observe(transport: WriteTransport) -> dict:
    _expect_snapshot(read_config(transport), 1200, 1000)
    transport.write_setting(FixedWrite.TEST_DPI_800)
    transport.write_setting(FixedWrite.TEST_POLLING_500)
    _expect_snapshot(read_config(transport), 800, 500)
    # This restoration is an explicit experiment step, only after confirmed
    # state. No close/error handler writes or restores anything.
    transport.write_setting(FixedWrite.RESTORE_DPI_1200)
    transport.write_setting(FixedWrite.RESTORE_POLLING_1000)
    _expect_snapshot(read_config(transport), 1200, 1000)
    return {"status": "settings_test_verified_and_restored", "usb_id": "3710:5406",
            "tested": {"dpi": 800, "polling_rate_hz": 500},
            "restored": {"dpi": 1200, "polling_rate_hz": 1000},
            "profile_index": 0, "active_stage_index": 2, "adapter_enabled": False}


class SettingsHidraw:
    def __init__(self, opened: HidrawProbe):
        self._opened = opened
        self._readers = [ConfigHidraw(opened)]
        self._read_calls = 0
        self.write_attempts = 0
        self.writes_completed = 0
        self.phase = "baseline_read"

    def exchange(self, query: ConfigQuery) -> Reply:
        if self._read_calls >= 36:
            raise ProbeBlocked("Experiment read budget exhausted.")
        self._read_calls += 1
        if self._readers[-1].sent >= 12:
            self._readers.append(ConfigHidraw(self._opened))
        return self._readers[-1].exchange(query)

    def write_setting(self, action: FixedWrite) -> None:
        packet = write_packet(action)
        if self.write_attempts >= 4 or action is not tuple(FixedWrite)[self.write_attempts]:
            raise ProbeBlocked("Only the fixed experiment write order is allowed.")
        self.phase = action.name.lower()
        self._opened.target.verify_cached_identity()
        check_competitors(self._opened.numbers)
        self.write_attempts += 1
        if os.write(self._opened.descriptor, packet) != len(packet):
            raise ProbeBlocked("Incomplete settings output; state may have changed. No retry or automatic restoration.")
        self.writes_completed += 1
        receive_write_ack(self._opened)
        if self.write_attempts == 2:
            self.phase = "test_readback"
        elif self.write_attempts == 4:
            self.phase = "restoration_readback"

    def diagnostics(self) -> dict:
        return {"phase": self.phase, "settings_writes_attempted": self.write_attempts,
                "settings_writes_completed": self.writes_completed,
                "output_reports_attempted": sum(reader.sent for reader in self._readers) + self.write_attempts,
                "output_reports_completed": sum(reader.completed for reader in self._readers) + self.writes_completed,
                "last_read": self._readers[-1].failure_summary()}


@contextmanager
def experiment_deadline() -> Iterator[None]:
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ProbeBlocked("Run the experiment as a standalone process.")
    def expired(_signum, _frame):
        raise ProbeBlocked("Settings experiment deadline reached; inspect state before any further action.")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--vendor-tools-closed", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(plan(), indent=2))
        return 0
    if not args.vendor_tools_closed:
        print(json.dumps({"status": "blocked", "detail": "Confirm competing control tools are closed first."}))
        return 2
    transport: SettingsHidraw | None = None
    try:
        if os.geteuid() == 0:
            raise ProbeBlocked("Do not run this experiment as root.")
        target = discover_target()
        with experiment_deadline(), open_probe(target, vendor_tools_closed=True) as opened:
            transport = SettingsHidraw(opened)
            result = observe(transport)
            result["diagnostics"] = transport.diagnostics()
        print(json.dumps(result, indent=2))
        return 0
    except (ProbeBlocked, OSError, ValueError, InvalidReply, ReplyTimeout, DeviceBusyError, OwnershipUnavailableError):
        print(json.dumps({"status": "blocked", "detail": "Experiment not confirmed. No retry or automatic restoration; inspect device state before continuing.",
                          "settings_may_have_changed": transport is not None and transport.write_attempts > 0,
                          "diagnostics": transport.diagnostics() if transport is not None else None}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Separately approved PSSTX21 identity/current-settings experiment.

Default mode prints a plan only. No settings writes, profile changes, scanning,
initialization/config-mode commands, retries or application activation exist here.
Packet layout references the MIT Nordic notes credited in pulsar_readonly.py.
"""

import argparse
import json
import os
from enum import Enum
from typing import Protocol

from pcc.diagnostics.pulsar_probe import (
    DESCRIPTOR_SHA256, HidrawProbe, ProbeBlocked, check_competitors,
    discover_target, open_probe, process_deadline,
)
from pcc.drivers.protocols.pulsar_readonly import (
    ExpectedReply, InvalidReply, Reply, ReplyTimeout, complemented_value,
    dpi_value, polling_rate, receive_reply,
)
from pcc.ownership import DeviceBusyError, OwnershipUnavailableError


class ConfigQuery(Enum):
    IDENTITY = (0x01, None, 8)
    PROFILE = (0x0E, None, 0)
    POLLING = (0x08, 0x0000, 2)
    STAGE_COUNT = (0x08, 0x0002, 2)
    ACTIVE_STAGE = (0x08, 0x0004, 2)
    DPI_0 = (0x08, 0x000C, 4)
    DPI_1 = (0x08, 0x0010, 4)
    DPI_2 = (0x08, 0x0014, 4)
    DPI_3 = (0x08, 0x0018, 4)
    DPI_4 = (0x08, 0x001C, 4)
    DPI_5 = (0x08, 0x0020, 4)


DPI_QUERIES = tuple(ConfigQuery)[5:]


def query_packet(query: ConfigQuery) -> bytes:
    if type(query) is not ConfigQuery:
        raise ValueError("Only fixed identity/current-settings queries are supported.")
    command, address, length = query.value
    packet = bytearray(17)
    packet[:2] = bytes((8, command))
    packet[5] = length
    if address is not None:
        packet[3:5] = address.to_bytes(2, "big")
    if query is ConfigQuery.IDENTITY:
        # Fixed public nonce; no machine identifier or cryptographic secret.
        packet[6:14] = bytes.fromhex("13 57 9b df 00 00 00 00")
    packet[16] = (0x55 - sum(packet[:16])) & 255
    return bytes(packet)


def plan() -> dict:
    return {
        "mode": "plan", "device_io": False, "usb_id": "3710:5406", "interface": 1,
        "descriptor_sha256": DESCRIPTOR_SHA256,
        "queries": [{"name": q.name.lower(), "packet_hex": query_packet(q).hex(" ")} for q in ConfigQuery],
        "sequence": ["identity", "profile", "stage_count", "active_stage", "polling", "active_stage_dpi_only",
                     "polling", "same_stage_dpi", "active_stage", "stage_count", "profile", "identity"],
        "maximum_output_reports": 12, "retries": 0,
        "receive_timeout_seconds_per_query": 0.5, "process_deadline_seconds": 8,
        "expected_identity": {"cid": 0x57, "mid": 0x27, "type": 5},
        "requires_separate_unvalidated_read_approval": True,
        "requires_vendor_tools_closed": True, "settings_adapter_activation": False,
    }


class ConfigTransport(Protocol):
    def exchange(self, query: ConfigQuery) -> Reply: ...


class ConfigHidraw:
    """Reuse descriptor/ownership lifecycle without widening the two-query tool."""

    def __init__(self, opened: HidrawProbe):
        self._opened = opened
        self.sent = 0
        self.completed = 0
        self.last_query: ConfigQuery | None = None
        self.phase = "preflight"
        self.reply_diagnostics: dict[str, int | bool] = {}

    def exchange(self, query: ConfigQuery) -> Reply:
        packet = query_packet(query)
        if self.sent >= 12:
            raise ProbeBlocked("Current-settings output budget exhausted.")
        self.last_query = query
        self.phase = "preflight"
        self.reply_diagnostics = {"reports_received": 0, "matching_command_reports": 0,
                                  "bad_checksum_reports": 0, "nonzero_status_reports": 0}
        self._opened.target.verify_cached_identity()
        check_competitors(self._opened.numbers)
        self.phase = "write"
        self.sent += 1
        if os.write(self._opened.descriptor, packet) != len(packet):
            raise ProbeBlocked("Incomplete query output; no retry will be sent.")
        self.completed += 1
        self.phase = "receive"
        command, address, length = query.value
        expected = ExpectedReply(command, address, length) if address is not None else ExpectedReply(command)
        result = receive_reply(self, expected, timeout_seconds=0.5, max_reports=32)
        self.phase = "decode"
        return result

    def read_report(self, timeout_seconds: float) -> bytes:
        packet = self._opened.read_report(timeout_seconds)
        details = self.reply_diagnostics
        details["reports_received"] += 1
        if (self.last_query is not None and len(packet) == 17
                and packet[0] == 8 and packet[1] == self.last_query.value[0]):
            details["matching_command_reports"] += 1
            details["last_payload_length"] = packet[5]
            if sum(packet) & 255 != 0x55:
                details["bad_checksum_reports"] += 1
            elif packet[2] != 0:
                details["nonzero_status_reports"] += 1
            elif self.last_query is ConfigQuery.IDENTITY:
                # Boolean projection only: never disclose nonce/unused identity bytes.
                details["expected_identity_fields_present"] = packet[10:13] == bytes((0x57, 0x27, 5))
            elif self.last_query.value[1] is not None:
                details["memory_echo_matches"] = (
                    int.from_bytes(packet[3:5], "big") == self.last_query.value[1]
                    and packet[5] == self.last_query.value[2]
                )
        return packet

    def failure_summary(self) -> dict:
        return {
            "last_query": self.last_query.name.lower() if self.last_query is not None else None,
            "phase": self.phase, "output_reports_attempted": self.sent,
            "output_reports_completed": self.completed, "reply_diagnostics": dict(self.reply_diagnostics),
        }


def _identity(reply: Reply) -> tuple[int, int, int]:
    if reply.command != 1 or len(reply.payload) < 7:
        raise InvalidReply("Model identity is unavailable.")
    identity = tuple(reply.payload[4:7])
    if identity != (0x57, 0x27, 5):
        raise ProbeBlocked("Reply does not identify the expected PSSTX21 8K wireless model.")
    return identity


def _profile(reply: Reply) -> int:
    if reply.command != 0x0E or not reply.payload or not 0 <= reply.payload[0] <= 3:
        raise InvalidReply("Current profile is unavailable.")
    return reply.payload[0]


def observe(transport: ConfigTransport) -> dict:
    identity = _identity(transport.exchange(ConfigQuery.IDENTITY))
    profile = _profile(transport.exchange(ConfigQuery.PROFILE))
    count = complemented_value(transport.exchange(ConfigQuery.STAGE_COUNT))
    if not 1 <= count <= 6:
        raise ProbeBlocked("DPI stage count is outside this experiment's bounds.")
    stage = complemented_value(transport.exchange(ConfigQuery.ACTIVE_STAGE))
    if stage >= count:
        raise ProbeBlocked("Active DPI stage is outside the reported stage count.")
    polling = transport.exchange(ConfigQuery.POLLING)
    dpi_query = DPI_QUERIES[stage]
    dpi = transport.exchange(dpi_query)
    hz, value = polling_rate(polling), dpi_value(dpi)
    if hz is None or value is None:
        raise ProbeBlocked("Unsupported polling or DPI encoding; no default is assumed.")
    if (transport.exchange(ConfigQuery.POLLING) != polling
            or transport.exchange(dpi_query) != dpi
            or complemented_value(transport.exchange(ConfigQuery.ACTIVE_STAGE)) != stage
            or complemented_value(transport.exchange(ConfigQuery.STAGE_COUNT)) != count
            or _profile(transport.exchange(ConfigQuery.PROFILE)) != profile
            or _identity(transport.exchange(ConfigQuery.IDENTITY)) != identity):
        raise ProbeBlocked("Settings changed during observation; snapshot discarded.")
    return {
        "status": "candidate_current_settings_observed", "usb_id": "3710:5406",
        "identity": {"cid": identity[0], "mid": identity[1], "type": identity[2]},
        "active_profile_index": profile, "stage_count": count, "active_stage_index": stage,
        "observed": {"dpi_candidate": value, "stored_polling_rate_hz_candidate": hz},
        # Only the requested setting records; never nonce replies or private addresses.
        "setting_records": {"polling_hex": polling.payload.hex(" "), "active_dpi_hex": dpi.payload.hex(" ")},
        "adapter_enabled": False, "settings_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Requires separate approval of this exact experiment.")
    parser.add_argument("--vendor-tools-closed", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(plan(), indent=2))
        return 0
    if not args.vendor_tools_closed:
        print(json.dumps({"status": "blocked", "detail": "Close competing control tools and confirm closure first."}))
        return 2
    transport: ConfigHidraw | None = None
    phase = "discovery"
    try:
        if os.geteuid() == 0:
            raise ProbeBlocked("Do not run this diagnostic as root.")
        target = discover_target()
        phase = "open"
        with process_deadline(), open_probe(target, vendor_tools_closed=True) as opened:
            transport = ConfigHidraw(opened)
            result = observe(transport)
            result["output_reports_sent"] = transport.sent
        result["ownership_basis"] = "operator_closed_vendor_tools_and_visible_handles_checked"
        print(json.dumps(result, indent=2))
        return 0
    except ProbeBlocked as error:
        failure = {"status": "blocked", "failure_kind": "safety_check", "detail": str(error)}
    except (OSError, ValueError, InvalidReply, ReplyTimeout, DeviceBusyError, OwnershipUnavailableError) as error:
        kind = ("reply_timeout" if isinstance(error, ReplyTimeout) else
                "invalid_reply" if isinstance(error, InvalidReply) else
                "permission_denied" if isinstance(error, PermissionError) else
                "io_error" if isinstance(error, OSError) else
                "ownership" if isinstance(error, (DeviceBusyError, OwnershipUnavailableError)) else "invalid_metadata")
        failure = {"status": "blocked", "failure_kind": kind,
                   "detail": "Current-settings query was not confirmed; no retry or settings command was sent."}
    failure["diagnostics"] = transport.failure_summary() if transport is not None else {
        "last_query": None, "phase": phase, "output_reports_attempted": 0, "output_reports_completed": 0,
    }
    print(json.dumps(failure))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

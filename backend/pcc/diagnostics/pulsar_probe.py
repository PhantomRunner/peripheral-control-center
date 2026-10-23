"""Reviewable two-query protocol experiment; default mode performs no device IO.

Execution on PSSTX21 requires separate approval of these unvalidated read queries.
This tool cannot write settings, initialize a session, scan commands or enable an adapter.
"""

import argparse
import hashlib
import json
import os
import select
import signal
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from pcc.drivers.protocols.pulsar_readonly import ExpectedReply, InvalidReply, ReplyTimeout, battery_reading, firmware_version, receive_reply
from pcc.ownership import DeviceBusyError, DeviceOwnership, OwnershipUnavailableError

DESCRIPTOR_SHA256 = "655f29b1550cd7903311346991d3a5dc54988ab7326ac30cdd6284a784489c5e"


class ProbeBlocked(Exception):
    pass


class FixedQuery(Enum):
    BATTERY = 0x04
    MOUSE_FIRMWARE = 0x12


def query_packet(query: FixedQuery) -> bytes:
    if type(query) is not FixedQuery:
        raise ValueError("Only the two fixed read queries are supported.")
    packet = bytearray(17)
    packet[0:2] = bytes((0x08, query.value))
    packet[16] = (0x55 - sum(packet[:16])) & 0xFF
    return bytes(packet)


def plan() -> dict:
    return {
        "mode": "plan", "device_io": False, "usb_id": "3710:5406", "interface": 1,
        "descriptor_sha256": DESCRIPTOR_SHA256,
        "queries": [{"name": query.name.lower(), "packet_hex": query_packet(query).hex(" ")} for query in FixedQuery],
        "maximum_output_reports": 2, "retries": 0,
        "receive_timeout_seconds_per_query": 0.75, "process_deadline_seconds": 8,
        "requires_separate_unvalidated_read_approval": True,
        "requires_vendor_tools_closed": True,
        "settings_adapter_activation": False,
    }


@dataclass(frozen=True)
class ProbeTarget:
    node: Path = field(repr=False)
    usb_node: Path = field(repr=False)
    hid: Path = field(repr=False)
    interface: Path = field(repr=False)

    def verify_cached_identity(self) -> None:
        usb = self.interface.parent
        if ((usb / "idVendor").read_text().strip().lower() != "3710"
                or (usb / "idProduct").read_text().strip().lower() != "5406"
                or (self.interface / "bInterfaceNumber").read_text().strip() != "01"
                or hashlib.sha256((self.hid / "report_descriptor").read_bytes()).hexdigest() != DESCRIPTOR_SHA256):
            raise ProbeBlocked("Receiver identity or cached report descriptor changed.")


def discover_target(sys_root: Path = Path("/sys/class/hidraw"), dev_root: Path = Path("/dev")) -> ProbeTarget:
    targets = []
    for entry in sys_root.iterdir():
        if not entry.name.startswith("hidraw") or not entry.name[6:].isdigit():
            continue
        hid = (entry / "device").resolve()
        try:
            fields = dict(line.split("=", 1) for line in (hid / "uevent").read_text().splitlines() if "=" in line)
            parts = fields.get("HID_ID", "").split(":")
            if len(parts) != 3 or tuple(int(part, 16) for part in parts) != (3, 0x3710, 0x5406):
                continue
            interface = next((parent for parent in hid.parents if (parent / "bInterfaceNumber").is_file()), None)
            if interface is None or (interface / "bInterfaceNumber").read_text().strip() != "01":
                continue
            usb = interface.parent
            bus = int((usb / "busnum").read_text())
            device = int((usb / "devnum").read_text())
            if not 1 <= bus <= 999 or not 1 <= device <= 999:
                raise ProbeBlocked("Invalid cached USB address.")
            target = ProbeTarget(dev_root / entry.name, dev_root / "bus" / "usb" / f"{bus:03}" / f"{device:03}", hid, interface)
            target.verify_cached_identity()
            targets.append(target)
        except (FileNotFoundError, StopIteration):
            continue
    if len(targets) != 1:
        raise ProbeBlocked("Expected exactly one matching receiver interface; no HID node was opened.")
    return targets[0]


def device_numbers(target: ProbeTarget) -> frozenset[int]:
    nodes = (target.node.lstat(), target.usb_node.lstat())
    if not all(stat.S_ISCHR(info.st_mode) for info in nodes):
        raise ProbeBlocked("Expected direct character-device nodes.")
    return frozenset(info.st_rdev for info in nodes)


def check_competitors(numbers: frozenset[int], proc_root: Path = Path("/proc")) -> int:
    """Check current-user handles to both hidraw and usbfs without opening devices.

    This is a point-in-time check, not an exclusive kernel claim. Vendor tools
    must also be closed by the operator to prevent their automatic reconnection.
    """
    uninspectable = 0
    for process in proc_root.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            for descriptor in (process / "fd").iterdir():
                try:
                    info = descriptor.stat()
                except FileNotFoundError:
                    continue
                if stat.S_ISCHR(info.st_mode) and info.st_rdev in numbers:
                    raise ProbeBlocked("Another process has a receiver handle. Close vendor tools before testing.")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            uninspectable += 1
    return uninspectable


@contextmanager
def process_deadline() -> Iterator[None]:
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ProbeBlocked("Run the diagnostic as a standalone process.")

    def expired(_signum, _frame):
        raise ProbeBlocked("Diagnostic process deadline reached.")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 8)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class ProbeTransport(Protocol):
    def send_query(self, query: FixedQuery) -> None: ...
    def read_report(self, timeout_seconds: float) -> bytes: ...


class HidrawProbe:
    def __init__(self, target: ProbeTarget, descriptor: int, numbers: frozenset[int]):
        self.target, self.descriptor, self.numbers = target, descriptor, numbers
        self.sent = 0

    def send_query(self, query: FixedQuery) -> None:
        packet = query_packet(query)
        if self.sent >= 2:
            raise ProbeBlocked("The diagnostic output budget is exhausted.")
        self.target.verify_cached_identity()
        check_competitors(self.numbers)
        self.sent += 1
        if os.write(self.descriptor, packet) != len(packet):
            raise ProbeBlocked("Incomplete query output; no retry will be sent.")

    def read_report(self, timeout_seconds: float) -> bytes:
        ready, _, _ = select.select([self.descriptor], [], [], timeout_seconds)
        if not ready:
            raise TimeoutError
        data = os.read(self.descriptor, 64)
        if not data:
            raise ProbeBlocked("Receiver input ended.")
        return data


@contextmanager
def open_probe(target: ProbeTarget, *, vendor_tools_closed: bool = False) -> Iterator[HidrawProbe]:
    if os.geteuid() == 0:
        raise ProbeBlocked("Do not run this diagnostic as root.")
    if vendor_tools_closed is not True:
        raise ProbeBlocked("The operator must close competing vendor tools before opening HID.")
    with DeviceOwnership().claim("pulsar_susanto_x"):
        target.verify_cached_identity()
        numbers = device_numbers(target)
        check_competitors(numbers)
        descriptor = os.open(target.node, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISCHR(info.st_mode) or info.st_rdev != target.node.lstat().st_rdev:
                raise ProbeBlocked("Receiver node changed while opening.")
            target.verify_cached_identity()
            check_competitors(numbers)
            yield HidrawProbe(target, descriptor, numbers)
        finally:
            os.close(descriptor)


def observe(transport: ProbeTransport) -> dict:
    observed = {}
    for query in FixedQuery:
        transport.send_query(query)
        reply = receive_reply(transport, ExpectedReply(query.value), timeout_seconds=0.75, max_reports=32)
        if query is FixedQuery.BATTERY:
            battery = battery_reading(reply)
            observed["battery_percent"] = battery.percent
            observed["charging"] = battery.charging
        else:
            observed["mouse_firmware_candidate"] = firmware_version(reply)
    # No raw reports, USB serials, pairing bytes or identifiable paths are output.
    return {"status": "candidate_read_replies_observed", "usb_id": "3710:5406", "device_model_verified": False, "adapter_enabled": False, "observed": observed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-access", action="store_true", help="Inspect cached metadata and process handles only; never open HID.")
    mode.add_argument("--execute", action="store_true", help="Only after separate approval of the two unvalidated read queries.")
    parser.add_argument("--vendor-tools-closed", action="store_true", help="Operator confirms vendor tools cannot reconnect during execution.")
    args = parser.parse_args(argv)
    if not args.check_access and not args.execute:
        print(json.dumps(plan(), indent=2))
        return 0
    if args.execute and not args.vendor_tools_closed:
        print(json.dumps({"status": "blocked", "detail": "Close vendor tools and confirm they cannot reconnect before execution."}))
        return 2
    try:
        if os.geteuid() == 0:
            raise ProbeBlocked("Do not run this diagnostic as root.")
        target = discover_target()
        if args.check_access:
            uninspectable = check_competitors(device_numbers(target))
            print(json.dumps({
                "status": "manual_tool_closure_required" if uninspectable else "access_preflight_passed",
                "uninspectable_process_count": uninspectable,
                "device_io": False, "execution_approved": False,
                "ownership_verified": False,
            }))
            if uninspectable:
                return 2
        else:
            with process_deadline(), open_probe(target, vendor_tools_closed=args.vendor_tools_closed) as transport:
                result = observe(transport)
            result["ownership_basis"] = "operator_closed_vendor_tools_and_visible_handles_checked"
            print(json.dumps(result, indent=2))
        return 0
    except ProbeBlocked as error:
        print(json.dumps({"status": "blocked", "detail": str(error)}))
    except (OSError, ValueError, InvalidReply, ReplyTimeout, DeviceBusyError, OwnershipUnavailableError):
        print(json.dumps({"status": "blocked", "detail": "Diagnostic failed or a query was not confirmed. No settings-write commands, retries or fallback are performed."}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

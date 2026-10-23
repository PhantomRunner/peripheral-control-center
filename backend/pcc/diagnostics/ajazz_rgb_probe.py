"""Fixed wired AK820 Pro experiment; plan-only until separately authorized.

Four Feature SETs: START, lighting config, static blue data, SAVE. SAVE may
persist settings in flash; this is not a firmware operation or a volatile claim.
No arbitrary packet/report-ID arguments, receiver fallback or automatic retry.
Reference: kabelklaus/ajazz-ak820-pro, commit 4b69f3cb57506f518e5b2f9f5f56e07e8b9411d6,
MIT, Copyright (c) 2026 kabelklaus. Full notice: drivers/protocols/LICENSE.ajazz-ak820-pro.
"""

import argparse
import fcntl
import hashlib
import json
import os
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from pcc.diagnostics.pulsar_probe import ProbeBlocked, ProbeTarget, check_competitors, device_numbers, process_deadline
from pcc.drivers.protocols.ajazz_readonly import InvalidControlAcknowledgement, parse_control_ack
from pcc.drivers.protocols.ajazz_rgb import static_rgb_payload
from pcc.ownership import DeviceBusyError, DeviceOwnership, OwnershipUnavailableError

DESCRIPTOR_SHA256 = "a28e1d82c9261a181f75ab65ee28dc2e66e003e6d9a5c337df3a124bb8e62c7f"
# Linux HIDIOCSFEATURE(65) / HIDIOCGFEATURE(65): fixed unnumbered 64-byte reports.
SET_FEATURE_65 = (3 << 30) | (65 << 16) | (ord("H") << 8) | 0x06
GET_FEATURE_65 = (3 << 30) | (65 << 16) | (ord("H") << 8) | 0x07


class FixedFeature(Enum):
    START = 0x18
    MODE_CONFIG = 0x13
    STATIC_BLUE_DATA = 0x01
    SAVE = 0x02


def feature_payload(action: FixedFeature) -> bytes:
    if type(action) is not FixedFeature:
        raise ValueError("Only the fixed four-step RGB experiment is supported.")
    payload = bytearray(64)
    if action is FixedFeature.STATIC_BLUE_DATA:
        payload[:4] = bytes((1, 0x40, 0x80, 0xFF))
        payload[9] = 3  # Three of five configured brightness levels; not measured luminance.
        payload[14:16] = bytes((0x55, 0xAA))
    else:
        payload[:2] = bytes((4, action.value))
        payload[8] = 0 if action is FixedFeature.SAVE else 1
    return bytes(payload)


def plan() -> dict:
    return {
        "mode": "plan", "device_io": False, "usb_id": "0c45:8009", "interface": 3,
        "usage_page": "ff13", "descriptor_sha256": DESCRIPTOR_SHA256,
        "transport": "HID feature reports, report ID 0, 64-byte payload / 65-byte SET ioctl buffer",
        "set_reports": [{"action": action.name.lower(), "payload_hex": feature_payload(action).hex(" ")} for action in FixedFeature],
        "get_reports": ["initial feature", "START ack", "MODE_CONFIG ack", "SAVE ack"],
        "maximum_feature_sets": 4, "maximum_feature_gets": 4, "retries": 0,
        "process_deadline_seconds": 8, "settle_seconds": 0.04,
        "requested_lighting": {"mode": "static", "color": "#4080ff", "brightness_level": 3, "maximum_brightness_level": 5},
        "settings_may_persist_in_flash": True, "automatic_restore": False,
        "requires_separate_settings_write_approval": True, "requires_vendor_tools_closed": True,
        "requires_owner_visual_confirmation": True, "rgb_readback_available": False,
        "device_model_verified": False, "adapter_enabled": False,
    }


@dataclass(frozen=True)
class AjazzTarget(ProbeTarget):
    def verify_cached_identity(self) -> None:
        usb = self.interface.parent
        if ((usb / "idVendor").read_text().strip().lower() != "0c45"
                or (usb / "idProduct").read_text().strip().lower() != "8009"
                or (self.interface / "bInterfaceNumber").read_text().strip() != "03"
                or hashlib.sha256((self.hid / "report_descriptor").read_bytes()).hexdigest() != DESCRIPTOR_SHA256):
            raise ProbeBlocked("Wired keyboard identity or cached control descriptor changed.")


def discover_target(sys_root: Path = Path("/sys/class/hidraw"), dev_root: Path = Path("/dev")) -> AjazzTarget:
    targets = []
    for entry in sys_root.iterdir():
        if not entry.name.startswith("hidraw") or not entry.name[6:].isdigit():
            continue
        hid = (entry / "device").resolve()
        try:
            fields = dict(line.split("=", 1) for line in (hid / "uevent").read_text().splitlines() if "=" in line)
            parts = fields.get("HID_ID", "").split(":")
            if len(parts) != 3 or tuple(int(part, 16) for part in parts) != (3, 0x0C45, 0x8009):
                continue
            interface = next((parent for parent in hid.parents if (parent / "bInterfaceNumber").is_file()), None)
            if interface is None or (interface / "bInterfaceNumber").read_text().strip() != "03":
                continue
            usb = interface.parent
            bus, device = int((usb / "busnum").read_text()), int((usb / "devnum").read_text())
            if not 1 <= bus <= 999 or not 1 <= device <= 999:
                raise ProbeBlocked("Invalid cached USB address.")
            target = AjazzTarget(dev_root / entry.name, dev_root / "bus" / "usb" / f"{bus:03}" / f"{device:03}", hid, interface)
            target.verify_cached_identity()
            targets.append(target)
        except FileNotFoundError:
            continue
    if len(targets) != 1:
        raise ProbeBlocked("Expected exactly one matching wired FF13 control interface.")
    return targets[0]


class FeatureTransport(Protocol):
    def get_feature(self) -> bytes: ...
    def send_feature(self, action: FixedFeature) -> None: ...


class HidrawFeatures:
    def __init__(self, target: AjazzTarget, descriptor: int, numbers: frozenset[int], *, static_color: str = "#4080ff", brightness_percent: int = 60):
        self.target, self.descriptor, self.numbers = target, descriptor, numbers
        self.set_attempts = self.set_completed = self.get_attempts = 0
        self.phase = "initial_feature"
        self.last_received_length: int | None = None
        self.last_ack_command: int | None = None
        self.last_ack_success: bool | None = None
        self._rgb_payload = static_rgb_payload(static_color, brightness_percent)

    def _preflight(self) -> None:
        self.target.verify_cached_identity()
        check_competitors(self.numbers)

    def get_feature(self) -> bytes:
        if self.get_attempts >= 4:
            raise ProbeBlocked("Feature-read budget exhausted.")
        self._preflight()
        self.get_attempts += 1
        buffer = bytearray(65)  # Only request report ID zero.
        count = fcntl.ioctl(self.descriptor, GET_FEATURE_65, buffer, True)
        self.last_received_length = count
        if count == 64:
            payload = bytes(buffer[:64])  # Linux unnumbered GET data starts at byte zero.
        elif count == 65 and buffer[0] == 0:
            payload = bytes(buffer[1:])
        else:
            raise ProbeBlocked("Feature reply length/report-ID framing is not supported; no padding or fallback.")
        known = payload[0] == 4 and payload[1] in {0x18, 0x13, 0x02} and payload[2] == 0
        self.last_ack_command = payload[1] if known else None
        self.last_ack_success = payload[3] == 1 if known else None
        return payload

    def send_feature(self, action: FixedFeature) -> None:
        payload = feature_payload(action)
        if action is FixedFeature.STATIC_BLUE_DATA:
            payload = self._rgb_payload
        if self.set_attempts >= 4 or action is not tuple(FixedFeature)[self.set_attempts]:
            raise ProbeBlocked("Only the fixed RGB experiment order is allowed.")
        self.phase = action.name.lower()
        self._preflight()
        self.set_attempts += 1
        count = fcntl.ioctl(self.descriptor, SET_FEATURE_65, bytearray(b"\0" + payload), True)
        if count not in (64, 65):
            raise ProbeBlocked("Incomplete feature output; settings may have changed. No retry.")
        self.set_completed += 1

    def diagnostics(self) -> dict:
        return {"phase": self.phase, "feature_sets_attempted": self.set_attempts,
                "feature_sets_completed": self.set_completed, "feature_gets_attempted": self.get_attempts,
                "last_received_length": self.last_received_length,
                "last_known_ack_command": self.last_ack_command, "last_known_ack_success": self.last_ack_success}


@contextmanager
def open_features(target: AjazzTarget, *, vendor_tools_closed: bool, static_color: str = "#4080ff", brightness_percent: int = 60) -> Iterator[HidrawFeatures]:
    if os.geteuid() == 0 or vendor_tools_closed is not True:
        raise ProbeBlocked("Run as the normal user after closing competing control tools.")
    with DeviceOwnership().claim("ajazz_ak820_pro"):
        target.verify_cached_identity()
        numbers = device_numbers(target)
        check_competitors(numbers)
        descriptor = os.open(target.node, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISCHR(info.st_mode) or info.st_rdev != target.node.lstat().st_rdev:
                raise ProbeBlocked("Wired control node changed while opening.")
            target.verify_cached_identity()
            check_competitors(numbers)
            yield HidrawFeatures(target, descriptor, numbers, static_color=static_color, brightness_percent=brightness_percent)
        finally:
            os.close(descriptor)


def observe(transport: FeatureTransport, *, color: str = "#4080ff", brightness_percent: int = 60) -> dict:
    static_rgb_payload(color, brightness_percent)  # Validate semantic intent before the first IO.
    initial = transport.get_feature()
    if len(initial) != 64:
        raise ProbeBlocked("Initial feature report is incomplete.")
    # An idle/previous reply is not telemetry. Never emit its unused bytes.
    for action in FixedFeature:
        transport.send_feature(action)
        time.sleep(0.04)
        if action in {FixedFeature.START, FixedFeature.MODE_CONFIG}:
            parse_control_ack(transport.get_feature(), action.value)
        elif action is FixedFeature.SAVE:
            acknowledgement = transport.get_feature()
            if len(acknowledgement) != 64 or acknowledgement[:4] != bytes((4, 2, 0, 1)):
                raise InvalidControlAcknowledgement("SAVE acknowledgement was not confirmed.")
    return {"status": "lighting_sequence_acknowledged_visual_check_required", "usb_id": "0c45:8009",
            "requested": {"mode": "static", "color": color.lower(), "brightness_level": brightness_percent // 20},
            "acknowledged_commands": [0x18, 0x13, 0x02],
            "actual_rgb": None, "battery_percent": None, "firmware_version": None,
            "persistence_verified": False, "device_model_verified": False, "adapter_enabled": False}


def observe_control(transport: FeatureTransport) -> dict:
    if len(transport.get_feature()) != 64:
        raise ProbeBlocked("Control feature report is incomplete.")
    return {"status": "control_report_received", "usb_id": "0c45:8009",
            "actual_rgb": None, "battery_percent": None, "firmware_version": None,
            "device_model_verified": False, "adapter_enabled": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-access", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--read-control", action="store_true", help="One GET only; never send a Feature SET.")
    mode.add_argument("--apply-rgb", action="store_true", help="Explicit validated static RGB Apply; memory-write consent required.")
    parser.add_argument("--vendor-tools-closed", action="store_true")
    parser.add_argument("--allow-device-memory-writes", action="store_true")
    parser.add_argument("--color")
    parser.add_argument("--brightness-percent", type=int)
    args = parser.parse_args(argv)
    if not args.apply_rgb and (args.color is not None or args.brightness_percent is not None or args.allow_device_memory_writes):
        parser.error("Settings arguments require --apply-rgb.")
    if not args.check_access and not args.execute and not args.read_control and not args.apply_rgb:
        print(json.dumps(plan(), indent=2))
        return 0
    transport: HidrawFeatures | None = None
    try:
        if os.geteuid() == 0:
            raise ProbeBlocked("Do not run as root.")
        if (args.execute or args.read_control or args.apply_rgb) and not args.vendor_tools_closed:
            raise ProbeBlocked("Close competing tools and confirm closure before execution.")
        if args.apply_rgb:
            if not args.allow_device_memory_writes:
                raise ProbeBlocked("Explicit device-memory write consent is required.")
            static_rgb_payload(args.color, args.brightness_percent)
        target = discover_target()
        if args.check_access:
            missing = check_competitors(device_numbers(target))
            print(json.dumps({"status": "manual_tool_closure_required" if missing else "access_preflight_passed",
                              "uninspectable_process_count": missing, "device_io": False, "ownership_verified": False}))
            return 2 if missing else 0
        options = {"vendor_tools_closed": args.vendor_tools_closed}
        if args.apply_rgb:
            options.update(static_color=args.color.lower(), brightness_percent=args.brightness_percent)
        with process_deadline(), open_features(target, **options) as transport:
            result = observe_control(transport) if args.read_control else observe(
                transport, color=args.color.lower() if args.apply_rgb else "#4080ff",
                brightness_percent=args.brightness_percent if args.apply_rgb else 60)
            if args.apply_rgb:
                result["status"] = "lighting_sequence_acknowledged"
            result["diagnostics"] = transport.diagnostics()
        print(json.dumps(result, indent=2))
        return 0
    except (ProbeBlocked, InvalidControlAcknowledgement, OSError, ValueError, DeviceBusyError, OwnershipUnavailableError):
        print(json.dumps({"status": "blocked", "detail": "Wired RGB experiment was not confirmed; no retry, restore or fallback. Settings may have changed.",
                          "settings_may_have_changed": transport is not None and transport.set_attempts > 0,
                          "diagnostics": transport.diagnostics() if transport is not None else None}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

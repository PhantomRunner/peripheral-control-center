"""Fixed single-frame FF68 validation. Invoked only with separate explicit consent.

One blue/white checkerboard replaces the TFT image. Only source AKS075 framing,
three FF13 SETs, four GETs, nine FF68 outputs; no alternative or automatic retry.
Data-interface replies are receipts of unknown semantics, not display readback.
"""
import os
import select
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

from pcc.diagnostics import ajazz_rgb_probe as rgb
from pcc.drivers.protocols.ajazz_studio import Command, command_payload, parse_ack, screen_config_payload, screen_test_payload

DATA_DESCRIPTOR = '949444322d886b5e812e965ab489434f765546581bfae8fb72df5185c0cb1169'


@dataclass(frozen=True)
class DataTarget(rgb.AjazzTarget):
    def verify_cached_identity(self) -> None:
        import hashlib
        usb = self.interface.parent
        if ((usb / 'idVendor').read_text().strip().lower() != '0c45'
                or (usb / 'idProduct').read_text().strip().lower() != '8009'
                or (self.interface / 'bInterfaceNumber').read_text().strip() != '02'
                or hashlib.sha256((self.hid / 'report_descriptor').read_bytes()).hexdigest() != DATA_DESCRIPTOR):
            raise rgb.ProbeBlocked('Wired keyboard FF68 identity/descriptor changed.')


def discover_data(sys_root: Path = Path('/sys/class/hidraw'), dev_root: Path = Path('/dev')) -> DataTarget:
    targets = []
    for entry in sys_root.iterdir():
        if not entry.name.startswith('hidraw') or not entry.name[6:].isdigit(): continue
        hid = (entry / 'device').resolve()
        try:
            fields = dict(line.split('=', 1) for line in (hid / 'uevent').read_text().splitlines() if '=' in line)
            parts = fields.get('HID_ID', '').split(':')
            if len(parts) != 3 or tuple(int(part, 16) for part in parts) != (3, 0x0C45, 0x8009): continue
            interface = next((parent for parent in hid.parents if (parent / 'bInterfaceNumber').is_file()), None)
            if interface is None or (interface / 'bInterfaceNumber').read_text().strip() != '02': continue
            usb = interface.parent
            bus, device = int((usb / 'busnum').read_text()), int((usb / 'devnum').read_text())
            if not 1 <= bus <= 999 or not 1 <= device <= 999: raise rgb.ProbeBlocked('Invalid cached USB address.')
            target = DataTarget(dev_root / entry.name, dev_root / 'bus' / 'usb' / f'{bus:03}/{device:03}', hid, interface)
            target.verify_cached_identity(); targets.append(target)
        except FileNotFoundError: continue
    if len(targets) != 1: raise rgb.ProbeBlocked('Expected exactly one exact wired FF68 interface.')
    return targets[0]


class ScreenTransport(Protocol):
    def get_feature(self) -> bytes: ...
    def set_control(self, index: int) -> None: ...
    def send_chunk(self, index: int) -> None: ...


class ScreenHidraw:
    def __init__(self, control: rgb.HidrawFeatures, target: DataTarget, data_fd: int, numbers: frozenset[int], payload: bytes | None = None):
        self.control, self.target, self.data_fd, self.numbers = control, target, data_fd, numbers
        self.set_attempts = self.set_completed = self.output_attempts = self.output_completed = self.receipts = 0
        self.phase = 'initial_feature'
        start = bytearray(command_payload(Command.START)); start[8] = 0
        self.payload = screen_test_payload() if payload is None else payload
        self.total_chunks = len(self.payload) // 4096
        if len(self.payload) % 4096 or not 1 <= self.total_chunks <= 961:
            raise rgb.ProbeBlocked('Screen payload exceeds the bounded transfer size.')
        config = bytearray(screen_config_payload()); config[8:10] = self.total_chunks.to_bytes(2, 'little')
        self.control_payloads = (bytes(start), bytes(config), command_payload(Command.SAVE))

    def preflight(self):
        self.control.target.verify_cached_identity(); self.target.verify_cached_identity()
        rgb.check_competitors(self.numbers)

    def get_feature(self) -> bytes:
        self.preflight()
        return self.control.get_feature()

    def set_control(self, index: int) -> None:
        if type(index) is not int or index != self.set_attempts or not 0 <= index < 3:
            raise rgb.ProbeBlocked('Screen control budget/order exceeded.')
        if index == 2 and self.output_completed != self.total_chunks:
            raise rgb.ProbeBlocked('Never finalize an incomplete transfer.')
        self.preflight(); self.phase = ('start', 'image_config', 'save')[index]
        self.set_attempts += 1
        count = rgb.fcntl.ioctl(self.control.descriptor, rgb.SET_FEATURE_65, bytearray(b'\0' + self.control_payloads[index]), True)
        if count not in (64,65): raise rgb.ProbeBlocked('Incomplete screen control output; no retry.')
        self.set_completed += 1

    def send_chunk(self, index: int) -> None:
        if type(index) is not int or index != self.output_attempts or not 0 <= index < self.total_chunks or self.set_completed != 2:
            raise rgb.ProbeBlocked('Screen data budget/order exceeded.')
        self.preflight(); self.phase = 'screen_data'; self.output_attempts += 1
        chunk = self.payload[index * 4096:(index + 1) * 4096]
        if os.write(self.data_fd, b'\0' + chunk) != 4097:
            raise rgb.ProbeBlocked('Incomplete screen data write; no retry.')
        self.output_completed += 1
        if not select.select([self.data_fd], [], [], .3)[0]:
            raise rgb.ProbeBlocked('No bounded data-interface receipt; no retry/finalization.')
        if len(os.read(self.data_fd, 65)) != 64:
            raise rgb.ProbeBlocked('Incomplete data-interface reply; no padding.')
        self.receipts += 1

    def diagnostics(self) -> dict:
        return {'phase': self.phase, 'feature_sets_attempted': self.set_attempts, 'feature_sets_completed': self.set_completed,
                'feature_gets_attempted': self.control.get_attempts, 'data_outputs_attempted': self.output_attempts,
                'data_outputs_completed': self.output_completed, 'data_receipts': self.receipts,
                'data_receipt_semantics_verified': False, 'data_reply_length': 64 if self.receipts else None}


@contextmanager
def open_screen(payload: bytes | None = None) -> Iterator[ScreenHidraw]:
    if os.geteuid() == 0: raise rgb.ProbeBlocked('Do not run as root.')
    target, data = rgb.discover_target(), discover_data()
    if target.interface.parent != data.interface.parent:
        raise rgb.ProbeBlocked('Control and data must belong to the same wired USB instance.')
    numbers = rgb.device_numbers(target) | rgb.device_numbers(data)
    rgb.check_competitors(numbers)
    with rgb.open_features(target, vendor_tools_closed=True) as control:
        control.numbers = numbers
        data.verify_cached_identity(); rgb.check_competitors(numbers)
        descriptor = os.open(data.node, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISCHR(info.st_mode) or info.st_rdev != data.node.lstat().st_rdev:
                raise rgb.ProbeBlocked('Data node changed while opening.')
            data.verify_cached_identity(); rgb.check_competitors(numbers)
            # Bounded drain prevents already queued reports being counted as transfer receipts.
            for _ in range(4):
                if not select.select([descriptor], [], [], 0)[0]: break
                os.read(descriptor, 65)
            if select.select([descriptor], [], [], 0)[0]:
                raise rgb.ProbeBlocked('Data interface is unexpectedly active before transfer.')
            yield ScreenHidraw(control, data, descriptor, numbers, payload)
        finally: os.close(descriptor)


def observe_screen(transport: ScreenTransport, chunks: int = 9) -> dict:
    if type(chunks) is not int or not 1 <= chunks <= 961: raise rgb.ProbeBlocked('Invalid transfer budget.')
    if len(transport.get_feature()) != 64: raise rgb.ProbeBlocked('Incomplete initial feature reply.')
    for index, command in ((0, Command.START), (1, Command.IMAGE)):
        transport.set_control(index); time.sleep(.04); parse_ack(transport.get_feature(), command)
    for index in range(chunks): transport.send_chunk(index)
    transport.set_control(2); time.sleep(.04); parse_ack(transport.get_feature(), Command.SAVE)
    return {'status': 'screen_transfer_completed_visual_check_required', 'operation': 'screen', 'usb_id': '0c45:8009',
            'requested': 'static 128×128 blue/white checkerboard', 'actual_settings': None, 'persistence_verified': False,
            'data_receipt_semantics_verified': False}

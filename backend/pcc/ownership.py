"""Nonblocking per-device ownership across cooperating PCC processes.

This lock cannot establish that Bibimbap or another vendor tool has released HID.
No device handles are opened here.
"""

import fcntl
import hashlib
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class DeviceBusyError(Exception):
    pass


class OwnershipUnavailableError(Exception):
    pass


class DeviceOwnership:
    def __init__(self, directory: Path | None = None) -> None:
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir()))
        self.directory = directory if directory is not None else runtime / f"pcc-{os.getuid()}-locks"

    @contextmanager
    def claim(self, device_id: str) -> Iterator[None]:
        descriptor: int | None = None
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = self.directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise OwnershipUnavailableError("Device ownership is unavailable.")
            name = hashlib.sha256(device_id.encode()).hexdigest() + ".lock"
            descriptor = os.open(self.directory / name, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise OwnershipUnavailableError("Device ownership is unavailable.")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DeviceBusyError("This device is already in use by PCC.") from None
        except OSError:
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
            raise OwnershipUnavailableError("Device ownership is unavailable.") from None
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
            raise
        try:
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)

"""Read-only USB enumeration. Does not open USB or HID devices.

On Linux, sysfs idVendor/idProduct files are readable without root.
Finding a dongle does NOT establish a live link to its mouse/keyboard.
"""

from pathlib import Path


def scan_usb_ids(root: Path = Path("/sys/bus/usb/devices")) -> set[str]:
    found: set[str] = set()
    try:
        paths = list(root.iterdir())
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return found

    for path in paths:
        try:
            vid = (path / "idVendor").read_text(encoding="ascii").strip().lower()
            pid = (path / "idProduct").read_text(encoding="ascii").strip().lower()
        except (OSError, UnicodeError):
            continue
        if len(vid) == 4 and len(pid) == 4:
            found.add(f"{vid}:{pid}")
    return found

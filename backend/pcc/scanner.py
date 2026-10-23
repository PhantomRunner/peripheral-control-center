"""Read-only USB enumeration. Does not open USB or HID devices.

On Linux, sysfs idVendor/idProduct files are readable without root.
Finding a dongle does NOT establish a live link to its mouse/keyboard.
"""

from pathlib import Path

from .models import DeviceSummary


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


def discover_devices(root: Path = Path("/sys/bus/usb/devices")) -> list[DeviceSummary]:
    present = scan_usb_ids(root)
    pulsar_receiver = "3710:5406" in present
    ajazz_wired = "0c45:8009" in present
    ajazz_receiver = "0c45:fdfd" in present

    return [
        DeviceSummary(
            id="pulsar_susanto_x",
            name="Pulsar Susanto-X",
            kind="mouse",
            status="receiver_detected" if pulsar_receiver else "offline",
            connected_usb_ids=["3710:5406"] if pulsar_receiver else [],
            note=(
                "8K receiver detected. The mouse link and settings are not read yet."
                if pulsar_receiver else "8K receiver not detected."
            ),
        ),
        DeviceSummary(
            id="ajazz_ak820_pro",
            name="AJAZZ AK820 Pro",
            kind="keyboard",
            status=(
                "wired_detected" if ajazz_wired else
                "receiver_detected" if ajazz_receiver else "offline"
            ),
            connected_usb_ids=[
                usb_id for usb_id, active in (
                    ("0c45:8009", ajazz_wired),
                    ("0c45:fdfd", ajazz_receiver),
                ) if active
            ],
            note=(
                "Wired USB device detected. HID settings are not read yet."
                if ajazz_wired else
                "Only the 2.4 GHz receiver is detected; this does not confirm keyboard connectivity."
                if ajazz_receiver else "Keyboard and receiver not detected."
            ),
        ),
    ]

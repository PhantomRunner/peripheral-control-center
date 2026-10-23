from pathlib import Path

from pcc.scanner import discover_devices, scan_usb_ids


def add_usb(root: Path, name: str, vid: str, pid: str) -> None:
    device = root / name
    device.mkdir()
    (device / "idVendor").write_text(vid + "\n", encoding="ascii")
    (device / "idProduct").write_text(pid + "\n", encoding="ascii")


def test_scan_usb_ids_reads_only_valid_devices(tmp_path: Path) -> None:
    add_usb(tmp_path, "1-1", "3710", "5406")
    (tmp_path / "unrelated").mkdir()
    assert scan_usb_ids(tmp_path) == {"3710:5406"}


def test_known_hardware_detected_without_inventing_telemetry(tmp_path: Path) -> None:
    add_usb(tmp_path, "1-1", "3710", "5406")
    add_usb(tmp_path, "2-1", "0C45", "8009")
    add_usb(tmp_path, "2-2", "0c45", "fdfd")
    mouse, keyboard = discover_devices(tmp_path)
    assert mouse.status == "receiver_detected"
    assert keyboard.status == "wired_detected"
    assert keyboard.connected_usb_ids == ["0c45:8009", "0c45:fdfd"]
    assert mouse.battery_percent is None
    assert mouse.dpi is None
    assert mouse.polling_rate_hz is None
    assert keyboard.battery_percent is None


def test_dongle_does_not_imply_keyboard_wired(tmp_path: Path) -> None:
    add_usb(tmp_path, "1-1", "0c45", "fdfd")
    keyboard = discover_devices(tmp_path)[1]
    assert keyboard.status == "receiver_detected"
    assert "does not confirm" in keyboard.note


def test_unknown_or_missing_sysfs_does_not_crash(tmp_path: Path) -> None:
    assert len(discover_devices(tmp_path / "missing")) == 2
    assert all(item.status == "offline" for item in discover_devices(tmp_path))

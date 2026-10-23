from typing import AbstractSet

import pytest

from pcc.drivers.registry import AdapterRegistry, DEFAULT_REGISTRY
from pcc.models import DeviceSummary


def test_registry_uses_only_registered_adapters_in_order() -> None:
    snapshots: list[AbstractSet[str]] = []

    class FakeAdapter:
        def __init__(self, device_id: str) -> None:
            self.device_id = device_id

        def get_summary(self, present_usb_ids: AbstractSet[str]) -> DeviceSummary:
            snapshots.append(present_usb_ids)
            return DeviceSummary(
                id=self.device_id,
                name="Fake device",
                kind="mouse",
                status="offline",
                note="Fake enumeration only.",
            )

    present = {"1234:5678"}
    registry = AdapterRegistry((FakeAdapter("first"), FakeAdapter("second")))
    assert [item.id for item in registry.get_summaries(present)] == ["first", "second"]
    assert snapshots == [frozenset(present), frozenset(present)]
    assert snapshots[0] is snapshots[1]
    assert isinstance(snapshots[0], frozenset)
    assert AdapterRegistry(()).get_summaries(present) == []


@pytest.mark.parametrize(
    ("present", "statuses", "connected_ids"),
    [
        (set(), ("offline", "offline"), ([], [])),
        ({"1234:5678"}, ("offline", "offline"), ([], [])),
        ({"3710:5406"}, ("receiver_detected", "offline"), (["3710:5406"], [])),
        ({"0c45:fdfd"}, ("offline", "receiver_detected"), ([], ["0c45:fdfd"])),
        (
            {"3710:5406", "0c45:fdfd"},
            ("receiver_detected", "receiver_detected"),
            (["3710:5406"], ["0c45:fdfd"]),
        ),
        ({"0c45:8009"}, ("offline", "wired_detected"), ([], ["0c45:8009"])),
        (
            {"3710:5406", "0c45:8009", "0c45:fdfd"},
            ("receiver_detected", "wired_detected"),
            (["3710:5406"], ["0c45:8009", "0c45:fdfd"]),
        ),
    ],
)
def test_default_registry_preserves_usb_presence_and_unknown_telemetry(
    present: set[str], statuses: tuple[str, str], connected_ids: tuple[list[str], list[str]]
) -> None:
    mouse, keyboard = DEFAULT_REGISTRY.get_summaries(present)
    assert (mouse.id, keyboard.id) == ("pulsar_susanto_x", "ajazz_ak820_pro")
    assert (mouse.name, keyboard.name) == ("Pulsar Susanto-X", "AJAZZ AK820 Pro")
    assert (mouse.kind, keyboard.kind) == ("mouse", "keyboard")
    assert (mouse.status, keyboard.status) == statuses
    assert (mouse.connected_usb_ids, keyboard.connected_usb_ids) == connected_ids
    for device in (mouse, keyboard):
        assert device.battery_percent is None
        assert device.dpi is None
        assert device.polling_rate_hz is None
        assert device.firmware_version is None
        assert device.connection.source == "usb_enumeration"
        assert device.connection.wireless_link_verified is None
        assert device.capabilities.model_dump() == {
            "usb_discovery": True,
            "battery_read": device.kind == "mouse",
            "dpi_read": device.kind == "mouse",
            "polling_rate_read": device.kind == "mouse",
            "firmware_read": device.kind == "mouse",
            "settings_write": device.kind == "mouse",
            "control_read": device.kind == "keyboard",
        }
        assert device.driver_state == ("read_write" if device.kind == "mouse" else "read_only")
    assert mouse.connection.wired_usb_present is False
    assert mouse.connection.receiver_usb_present == ("3710:5406" in present)
    assert keyboard.connection.wired_usb_present == ("0c45:8009" in present)
    assert keyboard.connection.receiver_usb_present == ("0c45:fdfd" in present)
    if mouse.status == "receiver_detected":
        assert mouse.note == "8K receiver detected. Readings update manually; wireless link is not verified."
    if keyboard.status == "receiver_detected":
        assert keyboard.note == (
            "Only the 2.4 GHz receiver is detected; this does not confirm keyboard connectivity."
        )
    if keyboard.status == "wired_detected":
        assert keyboard.note == "Wired USB device detected. HID settings are not read yet."


def test_registry_refresh_does_not_keep_disconnected_devices_present() -> None:
    online = DEFAULT_REGISTRY.get_summaries({"3710:5406", "0c45:8009"})
    offline = DEFAULT_REGISTRY.get_summaries(set())
    assert all(device.status == "offline" for device in offline)
    assert all(device.connected_usb_ids == [] for device in offline)
    assert [device.status for device in online] == ["receiver_detected", "wired_detected"]

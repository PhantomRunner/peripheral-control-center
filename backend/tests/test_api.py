from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.drivers import registry
from pcc.main import app


def test_health() -> None:
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("present", "statuses"),
    [
        (set(), ["offline", "offline"]),
        ({"3710:5406", "0c45:fdfd"}, ["receiver_detected", "receiver_detected"]),
        ({"0c45:8009"}, ["offline", "wired_detected"]),
    ],
)
def test_device_api_shape(
    monkeypatch: pytest.MonkeyPatch, present: set[str], statuses: list[str]
) -> None:
    enumerate_usb = Mock(return_value=present)
    monkeypatch.setattr(registry, "scan_usb_ids", enumerate_usb)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/api/devices")
    enumerate_usb.assert_called_once()
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"devices"}
    assert [item["id"] for item in payload["devices"]] == [
        "pulsar_susanto_x", "ajazz_ak820_pro"
    ]
    assert [item["status"] for item in payload["devices"]] == statuses
    assert [item["driver_state"] for item in payload["devices"]] == ["read_write", "read_only"]
    for item in payload["devices"]:
        assert set(item) == {
            "id", "name", "kind", "status", "connected_usb_ids", "battery_percent",
            "dpi", "polling_rate_hz", "driver_state", "note",
            "firmware_version", "capabilities", "connection",
            "telemetry_updated_at", "settings_updated_at", "write_options", "control_responded", "control_checked_at",
        }
        assert item["battery_percent"] is None
        assert item["dpi"] is None
        assert item["polling_rate_hz"] is None
        assert item["firmware_version"] is None
        assert item["telemetry_updated_at"] is None
        assert item["settings_updated_at"] is None
        assert item["capabilities"] == {
            "usb_discovery": True,
            "battery_read": item["kind"] == "mouse",
            "dpi_read": item["kind"] == "mouse",
            "polling_rate_read": item["kind"] == "mouse",
            "firmware_read": item["kind"] == "mouse",
            "settings_write": item["kind"] == "mouse",
            "control_read": item["kind"] == "keyboard",
        }
        assert item["write_options"] == ({"dpi": [800, 1200], "polling_rate_hz": [500, 1000],
                                           "profile_index": 0, "active_stage_index": 2, "firmware_version": "3.03"} if item["kind"] == "mouse" else None)
        assert item["connection"] == {
            "source": "usb_enumeration",
            "wired_usb_present": "0c45:8009" in item["connected_usb_ids"],
            "receiver_usb_present": any(
                usb_id in item["connected_usb_ids"] for usb_id in ("3710:5406", "0c45:fdfd")
            ),
            "wireless_link_verified": None,
        }


def test_untrusted_host_rejected() -> None:
    with TestClient(app, base_url="http://malicious.test") as client:
        response = client.get("/api/health")
    assert response.status_code == 400

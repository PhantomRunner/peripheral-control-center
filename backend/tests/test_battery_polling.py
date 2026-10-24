"""Fake-clock polling limits; real subprocess/HID access is forbidden by conftest."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.drivers import registry
from pcc.main import app
from pcc.telemetry import TelemetryBusy, TelemetryCooldown, TelemetryService, TelemetrySnapshot, TelemetryUnavailable
from pcc.telemetry_api import get_telemetry_service

URL = "/api/devices/pulsar_susanto_x/telemetry/poll"


@pytest.fixture
def polling(monkeypatch):
    present = {"3710:5406"}
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: present)
    now = [0.0]
    reader = Mock(return_value=TelemetrySnapshot(battery_percent=20, charging=False, firmware_version="3.03"))
    service = TelemetryService(reader, clock=lambda: now[0])
    return service, reader, now, present


def test_poll_interval_is_measured_from_completion_not_start(polling):
    service, reader, now, _ = polling
    def slow():
        now[0] += 8
        return TelemetrySnapshot(battery_percent=20, charging=False, firmware_version=None)
    reader.side_effect = slow
    service.read(vendor_tools_closed=True, polling=True)
    now[0] = 60
    with pytest.raises(TelemetryCooldown) as error:
        service.read(vendor_tools_closed=True, polling=True)
    assert error.value.retry_after == 8
    reader.assert_called_once()
    now[0] = 68
    service.read(vendor_tools_closed=True, polling=True)
    assert reader.call_count == 2


@pytest.mark.parametrize("failure", [False, True])
def test_manual_or_failed_read_also_delays_next_poll(polling, failure):
    service, reader, now, _ = polling
    if failure:
        reader.side_effect = TelemetryUnavailable
        with pytest.raises(TelemetryUnavailable):
            service.read(vendor_tools_closed=True)
    else:
        service.read(vendor_tools_closed=True)
    now[0] = 59.1
    with pytest.raises(TelemetryCooldown) as error:
        service.read(vendor_tools_closed=True, polling=True)
    assert error.value.retry_after == 1
    reader.assert_called_once()


def test_poll_does_not_overlap_or_start_hid_when_receiver_missing(polling):
    service, reader, _, present = polling
    service._operation_lock.acquire()
    try:
        with pytest.raises(TelemetryBusy):
            service.read(vendor_tools_closed=True, polling=True)
    finally:
        service._operation_lock.release()
    present.clear()
    with pytest.raises(TelemetryUnavailable):
        service.read(vendor_tools_closed=True, polling=True)
    reader.assert_not_called()


def test_poll_endpoint_is_protected_strict_and_shared_across_sessions(polling):
    service, reader, now, _ = polling
    app.dependency_overrides[get_telemetry_service] = lambda: service
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            def headers():
                token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
                return {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            first, other = headers(), headers()
            assert client.post(URL, json={"vendor_tools_closed": True}).status_code == 403
            assert client.post(URL, headers=first, json={"vendor_tools_closed": False}).status_code == 409
            assert client.post(URL, headers=first, json={"vendor_tools_closed": True, "interval": 1}).status_code == 422
            reader.assert_not_called()
            result = client.post(URL, headers=first, json={"vendor_tools_closed": True})
            assert result.status_code == 200 and result.json()["battery_percent"] == 20
            blocked = client.post(URL, headers=other, json={"vendor_tools_closed": True})
            assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"
            # A rejected early poll must not invalidate the last confirmed observation.
            assert client.get("/api/devices").json()["devices"][0]["battery_percent"] == 20
            reader.assert_called_once()
            now[0] = 60
            assert client.post(URL, headers=other, json={"vendor_tools_closed": True}).status_code == 200
            assert reader.call_count == 2
    finally:
        app.dependency_overrides.clear()

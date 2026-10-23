import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from pcc.drivers import registry
from pcc.main import app
from pcc.telemetry import TelemetryBusy, TelemetryService, TelemetrySnapshot, TelemetryUnavailable, read_pulsar_snapshot
from pcc.telemetry_api import get_telemetry_service

OBSERVATION = json.loads((Path(__file__).parent / "fixtures" / "pulsar_initial_observation.json").read_text())
URL = "/api/devices/pulsar_susanto_x/telemetry/read"


@pytest.fixture
def telemetry_client(monkeypatch: pytest.MonkeyPatch):
    present = {"3710:5406"}
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: present)
    reading = TelemetrySnapshot(battery_percent=20, charging=False, firmware_version="3.03", recorded_at=datetime(2026, 10, 23, 16, 12, 11, tzinfo=timezone.utc))
    reader = Mock(return_value=reading)
    service = TelemetryService(reader)
    app.dependency_overrides[get_telemetry_service] = lambda: service
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
            headers = {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            yield client, headers, reader, service, present
    finally:
        app.dependency_overrides.clear()


def test_enumeration_never_runs_hid_and_initial_values_are_unknown(telemetry_client):
    client, _headers, reader, _service, _present = telemetry_client
    for _ in range(3):
        mouse = client.get("/api/devices").json()["devices"][0]
        assert mouse["battery_percent"] is None
        assert mouse["firmware_version"] is None
        assert mouse["telemetry_updated_at"] is None
        assert mouse["capabilities"]["battery_read"] is True
        assert mouse["capabilities"]["firmware_read"] is True
        assert mouse["capabilities"]["settings_write"] is False
    reader.assert_not_called()


def test_explicit_read_is_timestamped_and_never_claims_dpi_polling_or_wireless_link(telemetry_client):
    client, headers, reader, _service, _present = telemetry_client
    result = client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    assert result.status_code == 200
    assert result.json()["battery_percent"] == 20
    assert result.json()["firmware_version"] == "3.03"
    reader.assert_called_once_with()
    mouse = client.get("/api/devices").json()["devices"][0]
    assert mouse["battery_percent"] == 20
    assert mouse["firmware_version"] == "3.03"
    assert mouse["telemetry_updated_at"] == result.json()["recorded_at"]
    assert mouse["dpi"] is None and mouse["polling_rate_hz"] is None
    assert mouse["connection"]["wireless_link_verified"] is None
    assert mouse["capabilities"]["settings_write"] is False


@pytest.mark.parametrize("body", [{}, {"vendor_tools_closed": "true"}, {"vendor_tools_closed": 1}, {"vendor_tools_closed": True, "command": 7}])
def test_input_cannot_override_the_fixed_query_set(telemetry_client, body):
    client, headers, reader, _service, _present = telemetry_client
    assert client.post(URL, headers=headers, json=body).status_code == 422
    reader.assert_not_called()


def test_session_and_operator_tool_closure_are_required(telemetry_client):
    client, headers, reader, _service, _present = telemetry_client
    assert client.post(URL, json={"vendor_tools_closed": True}).status_code == 403
    assert client.post(URL, headers=headers, json={"vendor_tools_closed": False}).status_code == 409
    reader.assert_not_called()


def test_disconnection_clears_prior_readings_without_triggering_io(telemetry_client):
    client, headers, reader, _service, present = telemetry_client
    client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    present.clear()
    mouse = client.get("/api/devices").json()["devices"][0]
    assert mouse["status"] == "offline" and mouse["battery_percent"] is None
    assert mouse["firmware_version"] is None and mouse["telemetry_updated_at"] is None
    assert client.post(URL, headers=headers, json={"vendor_tools_closed": True}).status_code == 503
    reader.assert_called_once()


def test_read_failure_clears_stale_fields_and_redacts_diagnostics(telemetry_client):
    client, headers, reader, _service, _present = telemetry_client
    client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    reader.side_effect = OSError("private machine path /secret/serial")
    response = client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    assert response.status_code == 503
    assert "secret" not in response.text and "serial" not in response.text
    assert client.get("/api/devices").json()["devices"][0]["battery_percent"] is None
    assert reader.call_count == 2


def test_overlapping_manual_reads_are_rejected(telemetry_client):
    client, headers, reader, service, _present = telemetry_client
    def nested():
        with pytest.raises(TelemetryBusy):
            service.read(vendor_tools_closed=True)
        return TelemetrySnapshot(battery_percent=0, charging=True, firmware_version=None)
    reader.side_effect = nested
    response = client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    assert response.status_code == 200
    assert response.json()["battery_percent"] == 0


def test_subprocess_reader_accepts_recorded_redacted_result_without_replaying_hardware(monkeypatch: pytest.MonkeyPatch):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(OBSERVATION["result"])))
    monkeypatch.setattr("pcc.telemetry.subprocess.run", run)
    snapshot = read_pulsar_snapshot()
    assert snapshot.battery_percent == 20 and snapshot.firmware_version == "3.03"
    args, options = run.call_args
    assert args[0][1:] == ["-m", "pcc.diagnostics.pulsar_probe", "--execute", "--vendor-tools-closed"]
    assert options["timeout"] == 10 and options["check"] is False
    assert "shell" not in options
    assert run.call_count == 1


@pytest.mark.parametrize("failure", ["exit", "malformed", "wrong_device", "timeout"])
def test_subprocess_failures_are_not_retried_or_disclosed(monkeypatch: pytest.MonkeyPatch, failure):
    result = dict(OBSERVATION["result"])
    if failure == "wrong_device":
        result["usb_id"] = "0c45:8009"
    run = Mock(return_value=SimpleNamespace(returncode=2 if failure == "exit" else 0, stdout="private /machine/path" if failure == "malformed" else json.dumps(result)))
    if failure == "timeout":
        run.side_effect = subprocess.TimeoutExpired("private /path", 10)
    monkeypatch.setattr("pcc.telemetry.subprocess.run", run)
    with pytest.raises(TelemetryUnavailable, match="^Battery/firmware read was not confirmed.$"):
        read_pulsar_snapshot()
    run.assert_called_once()

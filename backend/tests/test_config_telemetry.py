import copy
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.config_telemetry import ConfigReadUnavailable, ConfigSnapshot, read_pulsar_config
from pcc.drivers import registry
from pcc.main import app
from pcc.telemetry import TelemetryBusy, TelemetryService, TelemetrySnapshot
from pcc.telemetry_api import get_telemetry_service

OBSERVATION = json.loads((Path(__file__).parent / "fixtures" / "pulsar_config_observation.json").read_text())
URL = "/api/devices/pulsar_susanto_x/settings/read"


@pytest.fixture
def config_client(monkeypatch):
    present = {"3710:5406"}
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: present)
    reading = ConfigSnapshot(dpi=1200, polling_rate_hz=1000, active_profile_index=0, active_stage_index=2,
                             recorded_at=datetime(2026, 10, 23, 18, 30, 12, tzinfo=timezone.utc))
    config_reader = Mock(return_value=reading)
    battery_reader = Mock(return_value=TelemetrySnapshot(battery_percent=20, charging=False, firmware_version="3.03"))
    service = TelemetryService(battery_reader, config_reader=config_reader)
    app.dependency_overrides[get_telemetry_service] = lambda: service
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
            headers = {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            yield client, headers, config_reader, battery_reader, service, present
    finally:
        app.dependency_overrides.clear()


def test_explicit_config_read_is_separate_from_enumeration_and_battery(config_client):
    client, headers, reader, battery, service, present = config_client
    for _ in range(2):
        initial = client.get("/api/devices").json()["devices"][0]
        assert initial["dpi"] is None and initial["settings_updated_at"] is None
    reader.assert_not_called()
    battery.assert_not_called()
    response = client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    assert response.status_code == 200
    assert response.json()["dpi"] == 1200 and response.json()["polling_rate_hz"] == 1000
    mouse = client.get("/api/devices").json()["devices"][0]
    assert mouse["dpi"] == 1200 and mouse["polling_rate_hz"] == 1000
    assert mouse["settings_updated_at"] == response.json()["recorded_at"]
    assert mouse["battery_percent"] is None and mouse["telemetry_updated_at"] is None
    assert mouse["connection"]["wireless_link_verified"] is None
    assert mouse["capabilities"]["settings_write"] is False
    reader.assert_called_once()
    battery.assert_not_called()
    service.read(vendor_tools_closed=True)
    reader.side_effect = ConfigReadUnavailable
    assert client.post(URL, headers=headers, json={"vendor_tools_closed": True}).status_code == 503
    mouse = client.get("/api/devices").json()["devices"][0]
    assert mouse["dpi"] is None and mouse["polling_rate_hz"] is None and mouse["settings_updated_at"] is None
    assert mouse["battery_percent"] == 20 and mouse["telemetry_updated_at"] is not None
    present.clear()
    mouse = client.get("/api/devices").json()["devices"][0]
    assert mouse["battery_percent"] is None and mouse["settings_updated_at"] is None
    assert client.post(URL, headers=headers, json={"vendor_tools_closed": True}).status_code == 503
    assert reader.call_count == 2


@pytest.mark.parametrize(("body", "status"), [
    ({"vendor_tools_closed": False}, 409), ({}, 422),
    ({"vendor_tools_closed": "true"}, 422), ({"vendor_tools_closed": True, "dpi": 800}, 422),
])
def test_read_body_cannot_request_writes_or_bypass_operator_closure(config_client, body, status):
    client, headers, reader, *_rest = config_client
    assert client.post(URL, headers=headers, json=body).status_code == status
    assert client.post(URL, json={"vendor_tools_closed": True}).status_code == 403
    reader.assert_not_called()


def test_read_types_share_ownership_and_report_failures_without_paths(config_client):
    client, headers, reader, battery, service, _present = config_client
    def nested():
        with pytest.raises(TelemetryBusy):
            service.read(vendor_tools_closed=True)
        raise OSError("/private/serial")
    reader.side_effect = nested
    response = client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    assert response.status_code == 503
    assert "private" not in response.text and "serial" not in response.text
    battery.assert_not_called()
    service.read(vendor_tools_closed=True)  # The failed read released ownership.
    battery.assert_called_once()


def test_recorded_decoded_observation_is_validated_without_live_replay(monkeypatch):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(OBSERVATION["result"])))
    monkeypatch.setattr("pcc.config_telemetry.subprocess.run", run)
    reading = read_pulsar_config()
    assert (reading.dpi, reading.polling_rate_hz, reading.active_profile_index, reading.active_stage_index) == (1200, 1000, 0, 2)
    assert run.call_args.args[0][1:] == ["-m", "pcc.diagnostics.pulsar_config_probe", "--execute", "--vendor-tools-closed"]
    assert run.call_args.kwargs["timeout"] == 10 and "shell" not in run.call_args.kwargs
    run.assert_called_once()


@pytest.mark.parametrize(("key", "value"), [
    ("identity", {"cid": 87, "mid": 3, "type": 5}),
    ("active_stage_index", 5), ("output_reports_sent", 1), ("settings_writes", 1),
    ("observed", {"dpi_candidate": 1600, "stored_polling_rate_hz_candidate": 1000}),
    ("setting_records", {"polling_hex": "01 01", "active_dpi_hex": "77 77 00 67"}),
])
def test_bad_identity_partial_or_inconsistent_snapshots_do_not_populate_readings(monkeypatch, key, value):
    result = copy.deepcopy(OBSERVATION["result"])
    result[key] = value
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(result)))
    monkeypatch.setattr("pcc.config_telemetry.subprocess.run", run)
    with pytest.raises(ConfigReadUnavailable):
        read_pulsar_config()
    run.assert_called_once()


@pytest.mark.parametrize("failure", ["exit", "timeout", "json"])
def test_subprocess_failure_does_not_retry_or_disclose_diagnostics(monkeypatch, failure):
    run = Mock(return_value=SimpleNamespace(returncode=2 if failure == "exit" else 0, stdout="/private/path"))
    if failure == "timeout":
        run.side_effect = subprocess.TimeoutExpired("/private/path", 10)
    monkeypatch.setattr("pcc.config_telemetry.subprocess.run", run)
    with pytest.raises(ConfigReadUnavailable) as error:
        read_pulsar_config()
    assert "private" not in str(error.value)
    run.assert_called_once()

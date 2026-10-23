import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.drivers import registry
from pcc.keyboard_control import ControlSnapshot, ControlUnavailable, read_ajazz_control
from pcc.main import app
from pcc.telemetry import TelemetryService
from pcc.telemetry_api import get_telemetry_service

URL = "/api/devices/ajazz_ak820_pro/control/read"


@pytest.fixture
def control_client(monkeypatch):
    present = {"0c45:8009", "0c45:fdfd"}
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: present)
    reader = Mock(return_value=ControlSnapshot())
    service = TelemetryService(control_reader=reader)
    app.dependency_overrides[get_telemetry_service] = lambda: service
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
            headers = {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            yield client, headers, reader, present
    finally:
        app.dependency_overrides.clear()


def test_control_response_is_manual_timestamped_and_independent_of_telemetry(control_client):
    client, headers, reader, _present = control_client
    keyboard = client.get("/api/devices").json()["devices"][1]
    assert keyboard["control_responded"] is None and keyboard["control_checked_at"] is None
    reader.assert_not_called()
    response = client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    assert response.status_code == 200
    keyboard = client.get("/api/devices").json()["devices"][1]
    assert keyboard["control_responded"] is True
    assert keyboard["control_checked_at"] == response.json()["recorded_at"]
    assert keyboard["battery_percent"] is keyboard["firmware_version"] is None
    assert keyboard["connection"]["wireless_link_verified"] is None
    reader.assert_called_once()


def test_receiver_only_or_failed_reads_clear_the_control_observation(control_client):
    client, headers, reader, present = control_client
    client.post(URL, headers=headers, json={"vendor_tools_closed": True})
    reader.side_effect = ControlUnavailable
    assert client.post(URL, headers=headers, json={"vendor_tools_closed": True}).status_code == 503
    assert client.get("/api/devices").json()["devices"][1]["control_responded"] is None
    present.remove("0c45:8009")
    assert client.post(URL, headers=headers, json={"vendor_tools_closed": True}).status_code == 503
    assert reader.call_count == 2


def test_protection_and_strict_body_precede_any_control_io(control_client):
    client, headers, reader, _present = control_client
    assert client.post(URL, json={"vendor_tools_closed": True}).status_code == 403
    assert client.post(URL, headers=headers, json={"vendor_tools_closed": False}).status_code == 409
    assert client.post(URL, headers=headers, json={"vendor_tools_closed": True, "command": 2}).status_code == 422
    reader.assert_not_called()


def result():
    return {"status": "control_report_received", "usb_id": "0c45:8009", "actual_rgb": None,
            "battery_percent": None, "firmware_version": None, "device_model_verified": False, "adapter_enabled": False,
            "diagnostics": {"phase": "initial_feature", "feature_sets_attempted": 0, "feature_sets_completed": 0,
                            "feature_gets_attempted": 1, "last_received_length": 65,
                            "last_known_ack_command": 2, "last_known_ack_success": True}}


def test_child_arguments_allow_only_one_get_without_execute_or_settings(monkeypatch):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(result())))
    monkeypatch.setattr("pcc.keyboard_control.subprocess.run", run)
    assert read_ajazz_control().responded is True
    assert run.call_args.args[0][1:] == ["-m", "pcc.diagnostics.ajazz_rgb_probe", "--read-control", "--vendor-tools-closed"]
    assert run.call_args.kwargs["timeout"] == 10 and "shell" not in run.call_args.kwargs
    run.assert_called_once()


@pytest.mark.parametrize("change", ["writes", "telemetry", "framing", "json"])
def test_write_or_invented_telemetry_results_are_never_accepted(monkeypatch, change):
    value = result()
    if change == "writes":
        value["diagnostics"]["feature_sets_attempted"] = 1
    elif change == "telemetry":
        value["battery_percent"] = 0
    elif change == "framing":
        value["diagnostics"]["last_received_length"] = 63
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="private /path" if change == "json" else json.dumps(value)))
    monkeypatch.setattr("pcc.keyboard_control.subprocess.run", run)
    with pytest.raises(ControlUnavailable):
        read_ajazz_control()
    run.assert_called_once()

"""Mocked application mode; the recorded observation is never replayed to HID."""

import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.apply_settings import SettingsService
from pcc.diagnostics.ajazz_rgb_probe import FixedFeature, feature_payload
from pcc.drivers import ajazz_rgb as driver, registry
from pcc.drivers.protocols.ajazz_rgb import static_rgb_payload
from pcc.main import app
from pcc.settings_api import get_settings_service

URL = "/api/devices/ajazz_ak820_pro/settings/apply"
OBSERVED = json.loads((Path(__file__).parent / "fixtures" / "ajazz_rgb_observation.json").read_text())["result"]


def worker_result():
    result = copy.deepcopy(OBSERVED)
    result["status"] = "lighting_sequence_acknowledged"  # Synthetic application-mode result, not a second capture.
    return result


@pytest.fixture
def rgb_client(monkeypatch):
    present = {"0c45:8009", "0c45:fdfd"}
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: present)
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(worker_result())))
    monkeypatch.setattr(driver.subprocess, "run", run)
    service = SettingsService(ack_rgb_adapters={"ajazz_ak820_pro": driver.AjazzRgbAdapter()})
    app.dependency_overrides[get_settings_service] = lambda: service
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
            headers = {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            yield client, headers, run, present
    finally:
        app.dependency_overrides.clear()


def body():
    return {"settings": {"kind": "keyboard", "rgb": {"mode": "static", "color": "#4080ff", "brightness_percent": 60}},
            "vendor_tools_closed": True, "allow_device_memory_writes": True}


def test_actual_ack_contract_is_separate_from_verified_settings_readback(rgb_client):
    client, headers, run, _present = rgb_client
    response = client.post(URL, headers=headers, json=body())
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "acknowledged" and "settings" not in result
    assert result["requested_settings"] == body()["settings"]
    assert result["actual_settings"] is None and result["readback_available"] is False
    assert result["persistence_verified"] is False and result["may_persist"] is True
    assert result["feedback"] == "command_acknowledgements" and "acknowledged_commands" not in result
    args = run.call_args.args[0]
    assert args[1:] == ["-m", "pcc.diagnostics.ajazz_rgb_probe", "--apply-rgb", "--color", "#4080ff",
                        "--brightness-percent", "60", "--vendor-tools-closed", "--allow-device-memory-writes"]
    assert "--execute" not in args and "--read-control" not in args
    assert run.call_args.kwargs["timeout"] == 10 and "shell" not in run.call_args.kwargs
    run.assert_called_once()


@pytest.mark.parametrize(("key", "value", "status"), [
    ("vendor_tools_closed", False, 409), ("allow_device_memory_writes", False, 409),
    ("allow_device_memory_writes", "true", 422), ("command", 0xF0, 422),
])
def test_confirmation_and_strict_schema_precede_all_io(rgb_client, key, value, status):
    client, headers, run, _present = rgb_client
    request = body()
    request[key] = value
    assert client.post(URL, headers=headers, json=request).status_code == status
    assert client.post(URL, json=body()).status_code == 403
    run.assert_not_called()


def test_unsupported_brightness_or_receiver_only_never_sends_settings(rgb_client):
    client, headers, run, present = rgb_client
    request = body()
    request["settings"]["rgb"]["brightness_percent"] = 50
    assert client.post(URL, headers=headers, json=request).status_code == 422
    present.remove("0c45:8009")
    assert client.post(URL, headers=headers, json=body()).status_code == 409
    run.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "exit", "json", "wrong_color", "invented_rgb", "partial", "wrong_ack", "persistence"])
def test_uncertain_or_mismatched_feedback_never_becomes_success_or_retries(rgb_client, failure):
    client, headers, run, _present = rgb_client
    value = worker_result()
    if failure == "wrong_color":
        value["requested"]["color"] = "#ffffff"
    elif failure == "invented_rgb":
        value["actual_rgb"] = {"color": "#4080ff"}
    elif failure == "partial":
        value["diagnostics"]["feature_sets_completed"] = 3
    elif failure == "wrong_ack":
        value["acknowledged_commands"] = [24, 19, 240]
    elif failure == "persistence":
        value["persistence_verified"] = True
    run.return_value = SimpleNamespace(returncode=2 if failure == "exit" else 0,
                                       stdout="private /serial/path" if failure == "json" else json.dumps(value))
    if failure == "timeout":
        run.side_effect = subprocess.TimeoutExpired("/private/path", 10)
    response = client.post(URL, headers=headers, json=body())
    assert response.status_code == 502
    assert "private" not in response.text and "serial" not in response.text
    run.assert_called_once()


def test_blue_builder_exactly_matches_the_hardware_checked_data_packet():
    assert static_rgb_payload("#4080ff", 60) == feature_payload(FixedFeature.STATIC_BLUE_DATA)


@pytest.mark.parametrize("brightness", [0, 20, 40, 60, 80, 100])
def test_rgb_builder_has_only_bounded_color_and_brightness_fields(brightness):
    packet = static_rgb_payload("#123456", brightness)
    assert len(packet) == 64 and packet[:4] == bytes.fromhex("01 12 34 56")
    assert packet[9] == brightness // 20 and packet[14:16] == bytes.fromhex("55 aa")
    assert all(value == 0 for index, value in enumerate(packet) if index not in {0, 1, 2, 3, 9, 14, 15})


@pytest.mark.parametrize(("color", "brightness"), [("bad", 60), ("#1234567", 60), ("#123456", 50), ("#123456", True)])
def test_raw_or_unrepresentable_intents_are_rejected(color, brightness):
    with pytest.raises(ValueError):
        static_rgb_payload(color, brightness)

"""The registered production adapter is exercised only through fake sessions."""

import copy
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.apply_settings import SettingsService
from pcc.diagnostics.pulsar_settings_probe import FixedWrite, write_packet
from pcc.drivers import pulsar_settings as driver, registry
from pcc.drivers.protocols.pulsar_settings import dpi_packet, polling_packet
from pcc.drivers.protocols.pulsar_readonly import Reply
from pcc.config_telemetry import ConfigSnapshot
from pcc.main import app
from pcc.ownership import DeviceOwnership
from pcc.settings_api import get_settings_service
from pcc.telemetry import TelemetryService
from pcc.telemetry_api import get_telemetry_service

URL = "/api/devices/pulsar_susanto_x/settings/apply"
OBSERVED = json.loads((Path(__file__).parent / "fixtures" / "pulsar_config_observation.json").read_text())["result"]


def snapshot(dpi=800, hz=500, **changes):
    value = copy.deepcopy(OBSERVED)
    value["observed"] = {"dpi_candidate": dpi, "stored_polling_rate_hz_candidate": hz}
    value.update(changes)
    return value


@pytest.fixture
def live_adapter_client(monkeypatch, tmp_path):
    discover = Mock(return_value=object())
    monkeypatch.setattr(driver, "discover_target", discover)
    read = Mock(side_effect=[copy.deepcopy(OBSERVED), snapshot()])
    monkeypatch.setattr(driver, "read_config", read)
    monkeypatch.setattr(driver, "receive_reply", Mock(return_value=Reply(0x12, bytes((3, 3)))))
    monkeypatch.setattr(driver, "ConfigHidraw", Mock())
    monkeypatch.setattr(driver, "check_competitors", Mock())
    ack = Mock()
    monkeypatch.setattr(driver, "receive_write_ack", ack)
    write = Mock(return_value=17)
    monkeypatch.setattr(driver.os, "write", write)
    owner = DeviceOwnership(tmp_path / "locks")
    closed = Mock()
    @contextmanager
    def opened(target, **kwargs):
        assert kwargs == {"vendor_tools_closed": True}
        with owner.claim("pulsar_susanto_x"):
            try:
                yield SimpleNamespace(descriptor=99, send_query=Mock(), target=SimpleNamespace(verify_cached_identity=Mock()), numbers=frozenset({42}))
            finally:
                closed()
    monkeypatch.setattr(driver, "open_probe", opened)
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: {"3710:5406"})
    service = SettingsService({"pulsar_susanto_x": driver.PulsarSettingsAdapter()}, owner)
    telemetry = TelemetryService()
    app.dependency_overrides[get_settings_service] = lambda: service
    app.dependency_overrides[get_telemetry_service] = lambda: telemetry
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
            headers = {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            yield client, headers, discover, read, ack, write, owner, closed, telemetry
    finally:
        app.dependency_overrides.clear()


def body(dpi=800, hz=500, confirmed=True):
    return {"settings": {"kind": "mouse", "dpi": dpi, "polling_rate_hz": hz}, "vendor_tools_closed": confirmed}


def test_combined_apply_uses_only_hardware_verified_packets_and_one_ownership_scope(live_adapter_client):
    client, headers, _discover, read, ack, write, owner, closed, _telemetry = live_adapter_client
    response = client.post(URL, headers=headers, json=body())
    assert response.status_code == 200
    assert response.json()["settings"] == body()["settings"]
    assert write.call_args_list == [((99, write_packet(FixedWrite.TEST_DPI_800)),), ((99, write_packet(FixedWrite.TEST_POLLING_500)),)]
    assert ack.call_count == 2 and read.call_count == 2
    closed.assert_called_once()
    with owner.claim("pulsar_susanto_x"):
        pass


@pytest.mark.parametrize(("dpi", "hz", "final"), [(800, None, snapshot(hz=1000)), (None, 500, snapshot(dpi=1200))])
def test_partial_apply_writes_only_the_requested_setting(live_adapter_client, dpi, hz, final):
    client, headers, _discover, read, _ack, write, *_rest = live_adapter_client
    read.side_effect = [copy.deepcopy(OBSERVED), final]
    response = client.post(URL, headers=headers, json=body(dpi, hz))
    assert response.status_code == 200
    assert response.json()["settings"] == body(dpi, hz)["settings"]
    assert write.call_count == 1
    assert write.call_args.args[1] == (dpi_packet(dpi) if dpi is not None else polling_packet(hz))
    assert read.call_count == 2


@pytest.mark.parametrize(("dpi", "hz", "confirmed", "status"), [
    (800, 500, False, 409), (1600, 500, True, 422), (800, 8000, True, 422), (True, 500, True, 422),
])
def test_unconfirmed_or_untested_values_are_rejected_before_discovery(live_adapter_client, dpi, hz, confirmed, status):
    client, headers, discover, read, _ack, write, *_rest = live_adapter_client
    assert client.post(URL, headers=headers, json=body(dpi, hz, confirmed)).status_code == status
    discover.assert_not_called()
    read.assert_not_called()
    write.assert_not_called()


@pytest.mark.parametrize("changed", [{"active_profile_index": 1}, {"active_stage_index": 1}, {"stage_count": 4}, {"identity": {"cid": 87, "mid": 3, "type": 5}}])
def test_wrong_model_or_untested_slot_never_writes(live_adapter_client, changed):
    client, headers, _discover, read, _ack, write, _owner, closed, _telemetry = live_adapter_client
    read.side_effect = [snapshot(1200, 1000, **changed)]
    assert client.post(URL, headers=headers, json=body()).status_code == 502
    write.assert_not_called()
    closed.assert_called_once()


@pytest.mark.parametrize("changed", [snapshot(dpi=1200), snapshot(active_profile_index=1)])
def test_wrong_readback_does_not_report_success_retry_or_restore(live_adapter_client, changed):
    client, headers, _discover, read, _ack, write, _owner, closed, _telemetry = live_adapter_client
    read.side_effect = [copy.deepcopy(OBSERVED), changed]
    assert client.post(URL, headers=headers, json=body()).status_code == 502
    assert write.call_count == 2
    closed.assert_called_once()


def test_partial_apply_detects_unrequested_settings_changes(live_adapter_client):
    client, headers, _discover, read, _ack, write, *_rest = live_adapter_client
    read.side_effect = [copy.deepcopy(OBSERVED), snapshot(dpi=800, hz=500)]
    assert client.post(URL, headers=headers, json=body(dpi=800, hz=None)).status_code == 502
    write.assert_called_once()


def test_missing_ack_stops_with_uncertain_state_and_releases_lock(live_adapter_client):
    client, headers, _discover, read, ack, write, owner, closed, _telemetry = live_adapter_client
    ack.side_effect = driver.ReplyTimeout("private /machine/serial")
    response = client.post(URL, headers=headers, json=body())
    assert response.status_code == 502
    assert "private" not in response.text and "serial" not in response.text
    assert write.call_count == read.call_count == 1
    closed.assert_called_once()
    with owner.claim("pulsar_susanto_x"):
        pass


def test_busy_pcc_device_does_not_start_a_session_or_write(live_adapter_client):
    client, headers, _discover, read, _ack, write, owner, *_rest = live_adapter_client
    with owner.claim("pulsar_susanto_x"):
        assert client.post(URL, headers=headers, json=body()).status_code == 423
    read.assert_not_called()
    write.assert_not_called()


def test_live_packet_builders_exactly_match_tested_restoration_records():
    assert dpi_packet(800) == write_packet(FixedWrite.TEST_DPI_800)
    assert dpi_packet(1200) == write_packet(FixedWrite.RESTORE_DPI_1200)
    assert polling_packet(500) == write_packet(FixedWrite.TEST_POLLING_500)
    assert polling_packet(1000) == write_packet(FixedWrite.RESTORE_POLLING_1000)


def test_unverified_firmware_cannot_open_a_settings_write_path(live_adapter_client, monkeypatch):
    client, headers, _discover, read, _ack, write, *_rest = live_adapter_client
    monkeypatch.setattr(driver, "receive_reply", Mock(return_value=Reply(0x12, bytes((3, 4)))))
    assert client.post(URL, headers=headers, json=body()).status_code == 502
    read.assert_not_called()
    write.assert_not_called()


def test_apply_clears_config_observations_so_old_values_cannot_reappear(live_adapter_client):
    client, headers, _discover, _read, _ack, _write, _owner, _closed, telemetry = live_adapter_client
    telemetry._config_reader = Mock(return_value=ConfigSnapshot(dpi=1200, polling_rate_hz=1000, active_profile_index=0, active_stage_index=2))
    telemetry.read_config(vendor_tools_closed=True)
    assert client.get("/api/devices").json()["devices"][0]["dpi"] == 1200
    assert client.post(URL, headers=headers, json=body()).status_code == 200
    mouse = client.get("/api/devices").json()["devices"][0]
    assert mouse["dpi"] is None and mouse["settings_updated_at"] is None

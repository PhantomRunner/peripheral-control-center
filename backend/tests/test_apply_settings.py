from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from pcc.apply_settings import SettingsService
from pcc.main import app
from pcc.ownership import DeviceOwnership
from pcc.settings_api import get_settings_service


class FakeDpiAdapter:
    validation_reference = "synthetic-test-only"

    def __init__(self):
        self.calls = []
        self.dpi = 400
        self.bad_readback = False
        self.fail_write = False

    def validate_dpi(self, value):
        if not 10 <= value <= 32000 or value % 10:
            raise ValueError("Unsupported test step")

    @contextmanager
    def session(self):
        self.calls.append("open")
        try:
            yield self
        finally:
            self.calls.append("close")

    def write_dpi(self, value):
        self.calls.append(("write_dpi", value))
        if self.fail_write:
            raise OSError("private USB path and serial")
        self.dpi = value

    def read_dpi(self):
        self.calls.append("read_dpi")
        return None if self.bad_readback else self.dpi


@pytest.fixture
def apply_client(tmp_path: Path):
    adapter = FakeDpiAdapter()
    ownership = DeviceOwnership(tmp_path / "locks")
    service = SettingsService({"pulsar_susanto_x": adapter}, ownership)
    app.dependency_overrides[get_settings_service] = lambda: service
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
            headers = {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            yield client, headers, adapter, ownership
    finally:
        app.dependency_overrides.clear()


URL = "/api/devices/pulsar_susanto_x/settings/apply"
DPI = {"settings": {"kind": "mouse", "dpi": 800}}


def test_default_app_has_no_live_write_adapters():
    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
        response = client.post(URL, headers={"Origin": "http://127.0.0.1", "X-PCC-Client": "web", "X-PCC-Session": token}, json=DPI)
    assert response.status_code == 409
    assert "No validated" in response.json()["detail"]


def test_dpi_requires_explicit_protected_post_and_matching_readback(apply_client):
    client, headers, adapter, _ownership = apply_client
    assert client.post(URL, json=DPI).status_code == 403
    assert adapter.calls == []
    response = client.post(URL, headers=headers, json=DPI)
    assert response.status_code == 200
    assert response.json() == {"device_id": "pulsar_susanto_x", "status": "verified", "settings": {"kind": "mouse", "dpi": 800, "polling_rate_hz": None}}
    assert adapter.calls == ["open", ("write_dpi", 800), "read_dpi", "close"]


@pytest.mark.parametrize("body", [
    {"settings": {"kind": "mouse", "dpi": True}},
    {"settings": {"kind": "mouse", "dpi": 800.0}},
    {"settings": {"kind": "mouse", "dpi": "800"}},
    {"settings": {"kind": "mouse", "dpi": 0}},
    DPI | {"persist_to_flash": True},
    DPI | {"packet": [8, 7, 0]},
])
def test_invalid_or_raw_requests_never_open_the_adapter(apply_client, body):
    client, headers, adapter, _ownership = apply_client
    assert client.post(URL, headers=headers, json=body).status_code == 422
    assert adapter.calls == []


def test_unsupported_adapter_step_is_rejected_before_open(apply_client):
    client, headers, adapter, _ownership = apply_client
    assert client.post(URL, headers=headers, json={"settings": {"kind": "mouse", "dpi": 801}}).status_code == 422
    assert adapter.calls == []


def test_failed_readback_never_claims_success_or_rolls_back(apply_client):
    client, headers, adapter, _ownership = apply_client
    adapter.bad_readback = True
    response = client.post(URL, headers=headers, json=DPI)
    assert response.status_code == 502
    assert "may have changed" in response.json()["detail"]
    assert adapter.calls == ["open", ("write_dpi", 800), "read_dpi", "close"]


def test_write_failure_is_redacted_and_not_retried(apply_client):
    client, headers, adapter, ownership = apply_client
    adapter.fail_write = True
    response = client.post(URL, headers=headers, json=DPI)
    assert response.status_code == 502
    assert "private" not in response.text and "serial" not in response.text
    assert adapter.calls == ["open", ("write_dpi", 800), "close"]
    with ownership.claim("pulsar_susanto_x"):
        pass


def test_busy_device_never_opens_another_session(apply_client):
    client, headers, adapter, ownership = apply_client
    with ownership.claim("pulsar_susanto_x"):
        assert client.post(URL, headers=headers, json=DPI).status_code == 423
    assert adapter.calls == []


def test_validation_evidence_cannot_be_supplied_by_http(apply_client):
    client, headers, adapter, _ownership = apply_client
    adapter.validation_reference = ""
    assert client.post(URL, headers=headers, json=DPI).status_code == 409
    assert client.post(URL, headers=headers, json=DPI | {"validated": True}).status_code == 422
    assert adapter.calls == []

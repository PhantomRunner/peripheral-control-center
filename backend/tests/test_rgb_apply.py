from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from pcc.apply_settings import SettingsService
from pcc.drivers.protocols.ajazz_readonly import ControlAcknowledgement
from pcc.main import app
from pcc.ownership import DeviceOwnership
from pcc.settings import RgbSettings
from pcc.settings_api import get_settings_service

URL = "/api/devices/ajazz_ak820_pro/settings/apply"
RGB = {"settings": {"kind": "keyboard", "rgb": {"mode": "static", "color": "#AABBCC", "brightness_percent": 60}}}


class FakeRgbAdapter:
    validation_reference = "synthetic-test-only"
    volatile_writes_verified = True
    wired = True
    echo_only = False
    mismatch = False

    def __init__(self):
        self.calls = []
        self.current = None

    def wired_usb_present(self):
        return self.wired

    def validate_rgb(self, desired):
        if desired.brightness_percent % 20:
            raise ValueError("Synthetic adapter only supports 20-percent steps")

    @contextmanager
    def session(self):
        self.calls.append("open")
        try:
            yield self
        finally:
            self.calls.append("close")

    def write_volatile_rgb(self, desired):
        self.calls.append(("volatile_rgb", desired))
        self.current = desired

    def read_rgb(self):
        self.calls.append("read_rgb")
        if self.echo_only:
            return ControlAcknowledgement(0x13, 0)
        if self.mismatch:
            return RgbSettings(color="#000000", brightness_percent=0)
        return self.current


@pytest.fixture
def rgb_client(tmp_path: Path):
    adapter = FakeRgbAdapter()
    ownership = DeviceOwnership(tmp_path / "locks")
    service = SettingsService(ownership=ownership, rgb_adapters={"ajazz_ak820_pro": adapter})
    app.dependency_overrides[get_settings_service] = lambda: service
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
            headers = {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            yield client, headers, adapter, ownership
    finally:
        app.dependency_overrides.clear()


def test_volatile_rgb_requires_explicit_apply_and_real_readback(rgb_client):
    client, headers, adapter, _ownership = rgb_client
    assert client.post(URL, json=RGB).status_code == 403
    assert adapter.calls == []
    response = client.post(URL, headers=headers, json=RGB)
    assert response.status_code == 200
    assert response.json()["settings"]["rgb"] == {"mode": "static", "color": "#aabbcc", "brightness_percent": 60}
    assert adapter.calls == ["open", ("volatile_rgb", adapter.current), "read_rgb", "close"]


def test_receiver_only_mode_never_opens_rgb_session(rgb_client):
    client, headers, adapter, _ownership = rgb_client
    adapter.wired = False
    assert client.post(URL, headers=headers, json=RGB).status_code == 409
    assert adapter.calls == []


@pytest.mark.parametrize("evidence", ["missing_identity", "missing_volatile_proof"])
def test_missing_validation_prevents_rgb_write(rgb_client, evidence):
    client, headers, adapter, _ownership = rgb_client
    if evidence == "missing_identity":
        adapter.validation_reference = ""
    else:
        adapter.volatile_writes_verified = False
    assert client.post(URL, headers=headers, json=RGB).status_code == 409
    assert adapter.calls == []


@pytest.mark.parametrize("mode", ["echo_only", "mismatch"])
def test_echo_and_incorrect_rgb_never_count_as_verified_settings(rgb_client, mode):
    client, headers, adapter, _ownership = rgb_client
    setattr(adapter, mode, True)
    assert client.post(URL, headers=headers, json=RGB).status_code == 502
    assert len([call for call in adapter.calls if isinstance(call, tuple)]) == 1
    assert adapter.calls[-1] == "close"


def test_unsupported_brightness_is_rejected_before_open(rgb_client):
    client, headers, adapter, _ownership = rgb_client
    body = {"settings": {"kind": "keyboard", "rgb": {"color": "#112233", "brightness_percent": 55}}}
    assert client.post(URL, headers=headers, json=body).status_code == 422
    assert adapter.calls == []


def test_flash_option_is_not_part_of_the_rgb_api(rgb_client):
    client, headers, adapter, _ownership = rgb_client
    assert client.post(URL, headers=headers, json=RGB | {"save_to_flash": True}).status_code == 422
    assert adapter.calls == []


def test_rgb_claim_conflict_prevents_session(rgb_client):
    client, headers, adapter, ownership = rgb_client
    with ownership.claim("ajazz_ak820_pro"):
        assert client.post(URL, headers=headers, json=RGB).status_code == 423
    assert adapter.calls == []

import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from pcc.drivers import registry
from pcc.main import app
from pcc.ownership import DeviceOwnership
from pcc.profile_api import get_profile_store
from pcc.profiles import ProfileConflictError, ProfileStorageError, ProfileStore
from pcc.settings import ProfileDraft, ProfileUpdate

MOUSE = {"name": "Work", "device_id": "pulsar_susanto_x", "settings": {"kind": "mouse", "dpi": 800, "polling_rate_hz": 1000}}
KEYBOARD = {"name": "Evening", "device_id": "ajazz_ak820_pro", "settings": {"kind": "keyboard", "rgb": {"color": "#336699", "brightness_percent": 40}}}


@pytest.fixture
def profile_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = ProfileStore(tmp_path / "profiles")
    app.dependency_overrides[get_profile_store] = lambda: store
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: pytest.fail("Profile CRUD must not enumerate hardware"))
    try:
        with TestClient(app, base_url="http://127.0.0.1:5173") as client:
            token = client.get("/api/session", headers={"X-PCC-Client": "web"}).json()["token"]
            headers = {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}
            yield client, headers, store
    finally:
        app.dependency_overrides.clear()


def test_profile_crud_is_persistent_and_does_not_access_devices(profile_client):
    client, headers, store = profile_client
    assert client.get("/api/profiles").json() == {"profiles": []}
    created = client.post("/api/profiles", headers=headers, json=MOUSE)
    assert created.status_code == 201
    profile = created.json()
    assert profile["revision"] == 1
    assert ProfileStore(store.directory).list()[0].id == profile["id"]
    response = client.put(f"/api/profiles/{profile['id']}", headers=headers, json=MOUSE | {"name": "Travel", "revision": 1})
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert client.get("/api/profiles").json()["profiles"][0]["name"] == "Travel"
    assert client.request("DELETE", f"/api/profiles/{profile['id']}", headers=headers, json={"revision": 2}).status_code == 200
    assert ProfileStore(store.directory).list() == []
    assert os.stat(store.directory).st_mode & 0o777 == 0o700
    assert os.stat(store.directory / "profiles.json").st_mode & 0o777 == 0o600


def test_keyboard_profile_saves_rgb_intent_without_applying_it(profile_client):
    client, headers, _store = profile_client
    response = client.post("/api/profiles", headers=headers, json=KEYBOARD)
    assert response.status_code == 201
    assert response.json()["settings"]["rgb"] == {"mode": "static", "color": "#336699", "brightness_percent": 40}


def test_profile_mutations_require_a_session(profile_client):
    client, _headers, _store = profile_client
    assert client.post("/api/profiles", json=MOUSE).status_code == 403
    assert client.get("/api/profiles").json() == {"profiles": []}


@pytest.mark.parametrize("change", [
    {"name": "   "}, {"name": "private\nname"}, {"name": "x" * 65},
    {"device_id": "unknown"}, {"persist_to_flash": True},
    {"settings": {"kind": "mouse"}},
    {"settings": {"kind": "mouse", "dpi": True}},
    {"settings": {"kind": "mouse", "dpi": 800.0}},
    {"settings": {"kind": "mouse", "dpi": "800"}},
    {"settings": {"kind": "mouse", "dpi": 0}},
    {"settings": {"kind": "mouse", "dpi": 32001}},
    {"settings": {"kind": "mouse", "polling_rate_hz": 123}},
    {"settings": {"kind": "mouse", "polling_rate_hz": True}},
    {"settings": KEYBOARD["settings"]},
])
def test_invalid_profile_input_is_rejected_before_storage(profile_client, change):
    client, headers, _store = profile_client
    assert client.post("/api/profiles", headers=headers, json=MOUSE | change).status_code == 422
    assert client.get("/api/profiles").json() == {"profiles": []}


@pytest.mark.parametrize("rgb", [{"color": "red", "brightness_percent": 50}, {"color": "#123456", "brightness_percent": 101}, {"color": "#123456", "brightness_percent": True}, {"color": "#123456", "brightness_percent": 20, "packet": [1, 2]}])
def test_invalid_rgb_intent_is_rejected(profile_client, rgb):
    client, headers, _store = profile_client
    assert client.post("/api/profiles", headers=headers, json=KEYBOARD | {"settings": {"kind": "keyboard", "rgb": rgb}}).status_code == 422


def test_stale_edits_and_deletes_cannot_overwrite_a_newer_revision(profile_client):
    client, headers, _store = profile_client
    profile = client.post("/api/profiles", headers=headers, json=MOUSE).json()
    url = f"/api/profiles/{profile['id']}"
    assert client.put(url, headers=headers, json=MOUSE | {"name": "New", "revision": 1}).status_code == 200
    assert client.put(url, headers=headers, json=MOUSE | {"name": "Lost edit", "revision": 1}).status_code == 409
    assert client.request("DELETE", url, headers=headers, json={"revision": 1}).status_code == 409
    assert client.get("/api/profiles").json()["profiles"][0]["name"] == "New"
    assert client.put(url, headers=headers, json=KEYBOARD | {"revision": 2}).status_code == 409


def test_invalid_and_missing_ids_are_handled(profile_client):
    client, headers, _store = profile_client
    assert client.put("/api/profiles/not-a-profile-id", headers=headers, json=MOUSE | {"revision": 1}).status_code == 422
    assert client.put(f"/api/profiles/{'a' * 32}", headers=headers, json=MOUSE | {"revision": 1}).status_code == 404


def test_corrupt_storage_is_not_overwritten_and_errors_are_redacted(profile_client):
    client, headers, store = profile_client
    client.post("/api/profiles", headers=headers, json=MOUSE)
    target = store.directory / "profiles.json"
    target.write_text("private machine data /hidden/path")
    response = client.post("/api/profiles", headers=headers, json=KEYBOARD)
    assert response.status_code == 503
    assert response.json() == {"detail": "Local profile storage is unavailable."}
    assert target.read_text() == "private machine data /hidden/path"


def test_failed_atomic_replace_keeps_existing_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = ProfileStore(tmp_path / "profiles")
    saved = store.create(ProfileDraft.model_validate(MOUSE))
    before = (store.directory / "profiles.json").read_bytes()
    monkeypatch.setattr("pcc.profiles.os.replace", lambda *args: (_ for _ in ()).throw(OSError("private path")))
    with pytest.raises(ProfileStorageError, match="^Local profile storage is unavailable.$"):
        store.update(saved.id, ProfileUpdate.model_validate(MOUSE | {"revision": 1, "name": "Changed"}))
    assert (store.directory / "profiles.json").read_bytes() == before
    assert sorted(path.name for path in store.directory.iterdir()) == ["locks", "profiles.json"]


def test_profile_lock_is_shared_between_store_instances(tmp_path: Path):
    store = ProfileStore(tmp_path / "profiles")
    store.list()
    with DeviceOwnership(store.directory / "locks").claim("software_profiles"):
        with pytest.raises(ProfileConflictError):
            ProfileStore(store.directory).create(ProfileDraft.model_validate(MOUSE))


def test_symlink_storage_is_rejected_without_touching_target(tmp_path: Path):
    store = ProfileStore(tmp_path / "profiles")
    store.list()
    target = tmp_path / "private"
    target.write_text("unchanged")
    (store.directory / "profiles.json").symlink_to(target)
    with pytest.raises(ProfileStorageError):
        store.create(ProfileDraft.model_validate(MOUSE))
    assert target.read_text() == "unchanged"

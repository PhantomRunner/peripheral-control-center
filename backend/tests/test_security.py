from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field
import pytest

from pcc.main import app
from pcc.security import LocalSessionMiddleware, SessionStore


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: int = Field(ge=1, le=10)


@pytest.fixture
def protected_client():
    sessions = SessionStore()
    probe = FastAPI()
    probe.add_middleware(LocalSessionMiddleware, sessions=sessions)
    probe.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])

    @probe.post("/api/probe")
    def validate_only(body: StrictInput):
        return {"value": body.value}

    token = sessions.issue("http://127.0.0.1:5173").token
    with TestClient(probe, base_url="http://127.0.0.1:5173") as client:
        yield client, {"Origin": "http://127.0.0.1:5173", "X-PCC-Client": "web", "X-PCC-Session": token}


def test_session_bootstrap_requires_custom_header_and_has_no_cors():
    with TestClient(app, base_url="http://127.0.0.1:5173") as client:
        assert client.get("/api/session").status_code == 403
        response = client.get("/api/session", headers={"X-PCC-Client": "web", "Sec-Fetch-Site": "same-origin"})
        assert response.status_code == 200
        assert len(response.json()["token"]) >= 32
        assert response.headers["cache-control"] == "no-store"
        assert "access-control-allow-origin" not in response.headers
        assert client.get("/api/session", headers={"X-PCC-Client": "web", "Origin": "https://hostile.example"}).status_code == 403
        assert client.get("/api/session", headers={"X-PCC-Client": "web", "Sec-Fetch-Site": "same-site"}).status_code == 403


def test_valid_same_origin_json_is_accepted(protected_client):
    client, headers = protected_client
    response = client.post("/api/probe", headers=headers, json={"value": 3})
    assert response.status_code == 200
    assert response.json() == {"value": 3}


@pytest.mark.parametrize("change", [
    {"Origin": "https://hostile.example"}, {"Origin": "null"},
    {"Origin": "http://127.0.0.1:8000"}, {"Origin": "http://localhost:5173"},
    {"Origin": "http://127.0.0.1:5173/"}, {"Sec-Fetch-Site": "same-site"},
    {"Sec-Fetch-Site": "cross-site"}, {"X-PCC-Client": ""},
])
def test_cross_origin_and_simple_clients_are_rejected(protected_client, change):
    client, headers = protected_client
    assert client.post("/api/probe", headers=headers | change, json={"value": 3}).status_code == 403


def test_missing_origin_and_session_are_rejected(protected_client):
    client, headers = protected_client
    assert client.post("/api/probe", headers={k: v for k, v in headers.items() if k != "Origin"}, json={"value": 3}).status_code == 403
    assert client.post("/api/probe", headers=headers | {"X-PCC-Session": "invalid"}, json={"value": 3}).status_code == 401
    assert client.post("/api/probe", headers={k: v for k, v in headers.items() if k != "X-PCC-Session"}, json={"value": 3}).status_code == 401


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"])
def test_simple_content_types_are_rejected(protected_client, content_type):
    client, headers = protected_client
    assert client.post("/api/probe", headers=headers | {"Content-Type": content_type}, content='{"value":3}').status_code == 415


@pytest.mark.parametrize("body", [{"value": True}, {"value": "3"}, {"value": 3.0}, {"value": 0}, {"value": 11}, {"value": 3, "command": "anything"}])
def test_strict_request_models_reject_coercion_and_extra_keys(protected_client, body):
    client, headers = protected_client
    assert client.post("/api/probe", headers=headers, json=body).status_code == 422


def test_expired_session_cannot_be_reused_or_moved_between_origins():
    now = [0.0]
    sessions = SessionStore(clock=lambda: now[0])
    token = sessions.issue("http://127.0.0.1:5173").token
    assert sessions.valid(token, "http://127.0.0.1:5173")
    assert not sessions.valid(token, "http://127.0.0.1:8000")
    now[0] = sessions.lifetime_seconds
    assert not sessions.valid(token, "http://127.0.0.1:5173")


def test_session_storage_is_bounded():
    sessions = SessionStore()
    first = sessions.issue("http://127.0.0.1").token
    for _ in range(128):
        last = sessions.issue("http://127.0.0.1").token
    assert not sessions.valid(first, "http://127.0.0.1")
    assert sessions.valid(last, "http://127.0.0.1")


def test_untrusted_hosts_and_cors_preflight_are_not_allowed():
    with TestClient(app, base_url="http://hostile.example") as client:
        assert client.get("/api/session", headers={"X-PCC-Client": "web"}).status_code == 400
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.options("/api/session", headers={"Origin": "https://hostile.example", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-PCC-Client"})
        assert "access-control-allow-origin" not in response.headers

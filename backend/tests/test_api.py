from fastapi.testclient import TestClient

from pcc.main import app


def test_health() -> None:
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_device_api_shape() -> None:
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/api/devices")
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["devices"]] == [
        "pulsar_susanto_x", "ajazz_ak820_pro"
    ]
    assert all(item["driver_state"] == "not_implemented" for item in payload["devices"])


def test_untrusted_host_rejected() -> None:
    with TestClient(app, base_url="http://malicious.test") as client:
        response = client.get("/api/health")
    assert response.status_code == 400

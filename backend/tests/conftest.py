import pytest


@pytest.fixture(autouse=True)
def never_launch_live_telemetry_from_tests(monkeypatch: pytest.MonkeyPatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Tests must inject a fake telemetry reader or mock the diagnostic subprocess.")

    monkeypatch.setattr("pcc.telemetry.subprocess.run", forbidden)
    monkeypatch.setattr("pcc.drivers.pulsar_settings.discover_target", forbidden)

"""Reconnect races with fake discovery/readers only; no hardware access."""
from unittest.mock import Mock

import pytest

from pcc.config_telemetry import ConfigSnapshot
from pcc.drivers import registry
from pcc.keyboard_control import ControlSnapshot
from pcc.telemetry import TelemetryService, TelemetrySnapshot, TelemetryUnavailable


@pytest.mark.parametrize("operation,usb_id,field,snapshot", [
    ("read", "3710:5406", "battery_percent", TelemetrySnapshot(battery_percent=20, charging=False, firmware_version="3.03")),
    ("read_config", "3710:5406", "dpi", ConfigSnapshot(dpi=1200, polling_rate_hz=1000, active_profile_index=0, active_stage_index=2)),
    ("read_control", "0c45:8009", "control_responded", ControlSnapshot()),
])
@pytest.mark.parametrize("reconnect", [False, True])
def test_late_read_cannot_survive_observed_disconnect(monkeypatch, operation, usb_id, field, snapshot, reconnect):
    present = {usb_id}
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: present)
    reader = Mock()
    service = TelemetryService(reader, config_reader=reader, control_reader=reader)
    device_id = snapshot.device_id

    def disconnect_during_read():
        present.clear()
        service.summaries()
        if reconnect:
            present.add(usb_id)
            service.summaries()
        return snapshot

    reader.side_effect = disconnect_during_read
    with pytest.raises(TelemetryUnavailable):
        getattr(service, operation)(vendor_tools_closed=True)
    assert getattr(next(d for d in service.summaries() if d.id == device_id), field) is None
    reader.assert_called_once()  # No recovery replay.
    present.add(usb_id)
    reader.side_effect = None
    reader.return_value = snapshot
    getattr(service, operation)(vendor_tools_closed=True)  # Explicit fresh read recovers.
    assert getattr(next(d for d in service.summaries() if d.id == device_id), field) is not None


def test_final_passive_scan_rejects_removal_without_an_intermediate_dashboard_scan(monkeypatch):
    present = {"3710:5406"}
    monkeypatch.setattr(registry, "scan_usb_ids", lambda *args: present)
    def read():
        present.clear()
        return TelemetrySnapshot(battery_percent=20, charging=False, firmware_version=None)
    service = TelemetryService(read)
    with pytest.raises(TelemetryUnavailable):
        service.read(vendor_tools_closed=True)
    assert service.summaries()[0].battery_percent is None

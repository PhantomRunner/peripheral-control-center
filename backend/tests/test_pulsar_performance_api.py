import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.drivers import registry
from pcc.drivers.pulsar_performance import PerformanceUnavailable, read_performance
from pcc.main import app
from pcc.performance_api import PerformanceService, get_performance_service
from pcc.performance_models import DpiStage, PerformanceCapabilities, PerformanceSnapshot, SensorSnapshot
from pcc.telemetry import TelemetryService
from pcc.telemetry_api import get_telemetry_service

URL = '/api/devices/pulsar_susanto_x/performance/read'


def snapshot():
    return PerformanceSnapshot(firmware_version='3.03',active_profile_index=0,active_stage_index=2,stage_count=3,
                               stages=[DpiStage(index=i,x=800,y=800) for i in range(3)],
                               polling_rate_hz=1000,sensor=SensorSnapshot())


@pytest.fixture
def api(monkeypatch):
    present = {'3710:5406'}
    monkeypatch.setattr(registry,'scan_usb_ids',lambda *args:present)
    reader = Mock(return_value=snapshot())
    service = PerformanceService(reader,PerformanceCapabilities(snapshot_read=True))
    telemetry = TelemetryService(reader=Mock(side_effect=AssertionError('No live telemetry')))
    app.dependency_overrides[get_performance_service] = lambda:service
    app.dependency_overrides[get_telemetry_service] = lambda:telemetry
    try:
        with TestClient(app,base_url='http://127.0.0.1:5173') as client:
            token = client.get('/api/session',headers={'X-PCC-Client':'web'}).json()['token']
            headers = {'Origin':'http://127.0.0.1:5173','X-PCC-Client':'web','X-PCC-Session':token}
            yield client,headers,reader,present,service,telemetry
    finally:
        app.dependency_overrides.clear()


def test_read_requires_protection_and_explicit_consent(api):
    client,headers,reader,*_ = api
    assert client.post(URL,json={'vendor_tools_closed':True}).status_code == 403
    for body in [{},{'vendor_tools_closed':False},{'vendor_tools_closed':1},{'vendor_tools_closed':True,'address':1}]:
        assert client.post(URL,headers=headers,json=body).status_code in {409,422}
    reader.assert_not_called()
    response = client.post(URL,headers=headers,json={'vendor_tools_closed':True})
    assert response.status_code == 200
    assert response.json()['sensor']['rotation'] is None
    reader.assert_called_once()


def test_disabled_support_offline_busy_and_failure_are_bounded(api):
    client,headers,reader,present,service,telemetry = api
    body = {'vendor_tools_closed':True}
    service.capabilities = PerformanceCapabilities()
    assert client.post(URL,headers=headers,json=body).status_code == 409
    service.capabilities = PerformanceCapabilities(snapshot_read=True)
    present.clear()
    assert client.post(URL,headers=headers,json=body).status_code == 503
    present.add('3710:5406')
    telemetry._operation_lock.acquire()
    try:
        assert client.post(URL,headers=headers,json=body).status_code == 423
    finally:
        telemetry._operation_lock.release()
    reader.assert_not_called()
    reader.side_effect = PerformanceUnavailable('/private/serial/path')
    response = client.post(URL,headers=headers,json=body)
    assert response.status_code == 503 and 'private' not in response.text
    reader.assert_called_once()


def test_disconnect_or_intervening_apply_rejects_late_snapshot(api):
    client,headers,reader,present,_service,telemetry = api
    def disconnected():
        present.clear()
        return snapshot()
    reader.side_effect = disconnected
    assert client.post(URL,headers=headers,json={'vendor_tools_closed':True}).status_code == 503
    present.add('3710:5406')
    def changed():
        telemetry.invalidate_config()
        return snapshot()
    reader.side_effect = changed
    assert client.post(URL,headers=headers,json={'vendor_tools_closed':True}).status_code == 503
    assert reader.call_count == 2


@pytest.mark.parametrize('bad', [None,'count','firmware','write','oversize'])
def test_child_boundary_validates_finite_result_and_never_retries(monkeypatch,bad):
    data = {'status':'performance_observed','snapshot':snapshot().model_dump(mode='json'),
            'output_reports_sent':34,'settings_write_reports':0,'adapter_activation':False}
    if bad == 'count': data['output_reports_sent'] = 33
    if bad == 'firmware': data['snapshot']['firmware_version'] = '3.04'
    if bad == 'write': data['settings_write_reports'] = 1
    raw = 'x'*16385 if bad == 'oversize' else json.dumps(data)
    run = Mock(return_value=SimpleNamespace(returncode=0,stdout=raw))
    monkeypatch.setattr('pcc.drivers.pulsar_performance.subprocess.run',run)
    if bad:
        with pytest.raises(PerformanceUnavailable): read_performance()
    else:
        assert read_performance().active_stage_index == 2
    run.assert_called_once()
    args,kwargs = run.call_args
    assert args[0][1:] == ['-m','pcc.diagnostics.pulsar_performance_probe','--execute','--vendor-tools-closed']
    assert kwargs['timeout'] == 26 and 'shell' not in kwargs

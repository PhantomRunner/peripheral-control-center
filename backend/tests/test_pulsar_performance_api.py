import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.drivers import registry
from pcc.drivers.pulsar_performance import PerformanceUnavailable, apply_performance,read_performance
from pcc.main import app
from pcc.performance_api import PerformanceService, get_performance_service
from pcc.performance_models import DpiStage, ParameterCapability,PerformanceApplyRequest,PerformanceCapabilities, PerformanceSnapshot, SensorSnapshot
from pcc.telemetry import TelemetryService
from pcc.telemetry_api import get_telemetry_service
from pcc.performance_support import validated_capabilities

URL = '/api/devices/pulsar_susanto_x/performance/read'
OBSERVATION=json.loads((Path(__file__).parent/'fixtures/pulsar_performance_observation.json').read_text())


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


def test_approved_observation_enables_explicit_production_reads_only(api):
    client,headers,reader,_present,service,_telemetry=api
    service.capabilities=validated_capabilities()
    reading=PerformanceSnapshot.model_validate_json(json.dumps(OBSERVATION['result']['snapshot']))
    reader.return_value=reading
    service.writer=Mock(side_effect=AssertionError('Reads must never enable writes'))
    discovery=client.get('/api/devices').json()['devices'][0]
    assert discovery['performance_capabilities']['snapshot_read'] is True
    assert all(p['read'] and not p['write'] and not p['values'] for p in discovery['performance_capabilities']['parameters'].values())
    reader.assert_not_called()
    assert discovery['dpi'] is discovery['firmware_version'] is None
    assert client.post(URL,headers=headers,json={}).status_code==409
    response=client.post(URL,headers=headers,json={'vendor_tools_closed':True})
    assert response.status_code==200 and response.json()==reading.model_dump(mode='json')
    assert [stage['x'] for stage in response.json()['stages']]==[400,800,1200,1800,3200]
    reader.assert_called_once()
    assert client.post(APPLY_URL,headers=headers,json=APPLY_BODY).status_code==409
    service.writer.assert_not_called()
    # Reading returns a timestamped snapshot, never invented discovery telemetry.
    assert client.get('/api/devices').json()['devices'][0]['dpi'] is None


def test_recorded_exact_device_observation_validates_without_hardware_replay(monkeypatch):
    run=Mock(return_value=SimpleNamespace(returncode=0,stdout=json.dumps(OBSERVATION['result'])))
    monkeypatch.setattr('pcc.drivers.pulsar_performance.subprocess.run',run)
    actual=read_performance()
    assert actual.active_profile_index==0 and actual.active_stage_index==2 and actual.stage_count==5
    assert actual.sensor.debounce==2 and actual.sensor.lod==1.0
    assert actual.sensor.rotation==0 and actual.sensor.rotation_enabled is False
    assert OBSERVATION['settings_write_reports']==0 and OBSERVATION['raw_reports_included'] is False
    assert OBSERVATION['elapsed_seconds']==1.044
    run.assert_called_once()


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


APPLY_URL=URL.replace('/read','/apply')
APPLY_BODY={'action':{'operation':'stage_dpi','stage_index':0,'dpi':1200},'expected_profile_index':0,
            'expected_active_stage_index':2,'vendor_tools_closed':True,'allow_device_memory_writes':True}


def enable_fake_write(service):
    service.capabilities=PerformanceCapabilities(snapshot_read=True,parameters={
        'stage_dpi':ParameterCapability(read=True,write=True,values=[1200])})
    actual=snapshot().model_copy(update={'stages':[DpiStage(index=i,x=1200 if i==0 else 800,y=1200 if i==0 else 800) for i in range(3)]})
    service.writer=Mock(return_value=actual)
    return actual


def test_apply_rejects_unvalidated_support_and_requires_both_consents(api):
    client,headers,reader,_present,service,_telemetry=api
    service.writer=Mock(side_effect=AssertionError('Gated write'))
    assert client.post(APPLY_URL,headers=headers,json=APPLY_BODY).status_code==409
    enable_fake_write(service)
    assert client.post(APPLY_URL,json=APPLY_BODY).status_code==403
    assert client.post(APPLY_URL,headers={**headers,'Origin':'http://foreign.example'},json=APPLY_BODY).status_code==403
    for patch in [{'vendor_tools_closed':False},{'allow_device_memory_writes':False},{'action':{'operation':'raw','address':1}}, {'raw_packet':'00'}]:
        assert client.post(APPLY_URL,headers=headers,json={**APPLY_BODY,**patch}).status_code in {409,422}
    service.writer.assert_not_called()
    response=client.post(APPLY_URL,headers=headers,json=APPLY_BODY)
    assert response.status_code==200 and response.json()['status']=='verified'
    assert response.json()['actual']['stages'][0]['x']==1200 and response.json()['persistence_verified'] is False
    reader.assert_not_called()
    service.writer.assert_called_once()


@pytest.mark.parametrize('failure',['busy','offline','mismatch','profile','stage','exception'])
def test_apply_does_not_claim_partial_or_unrelated_success(api,failure):
    client,headers,_reader,present,service,telemetry=api
    actual=enable_fake_write(service)
    if failure=='busy':telemetry._operation_lock.acquire()
    if failure=='offline':present.clear()
    if failure=='mismatch':service.writer.return_value=snapshot()
    if failure=='profile':service.writer.return_value=actual.model_copy(update={'active_profile_index':1})
    if failure=='stage':service.writer.return_value=actual.model_copy(update={'active_stage_index':1})
    if failure=='exception':service.writer.side_effect=PerformanceUnavailable('/private/serial')
    try:
        response=client.post(APPLY_URL,headers=headers,json=APPLY_BODY)
    finally:
        if failure=='busy':telemetry._operation_lock.release()
    assert response.status_code==(423 if failure=='busy' else 502)
    assert 'private' not in response.text
    assert service.writer.call_count==(0 if failure in {'busy','offline'} else 1)


@pytest.mark.parametrize('bad',[None,'count','write','intent','readback','profile','timeout'])
def test_apply_child_results_are_bounded_and_semantically_verified(monkeypatch,bad):
    actual=snapshot()
    body={**APPLY_BODY,'action':{'operation':'stage_dpi','stage_index':0,'dpi':800}}
    data={'result':{'status':'verified','requested':body['action'],'actual':actual.model_dump(mode='json'),
                    'persistence_verified':False,'may_persist':True},'output_reports_sent':69,'settings_write_reports':1}
    if bad=='count':data['output_reports_sent']=68
    if bad=='write':data['settings_write_reports']=2
    if bad=='intent':data['result']['requested']={'operation':'stage_dpi','stage_index':1,'dpi':800}
    if bad=='readback':data['result']['actual']['stages'][0]['x']=1200
    if bad=='profile':data['result']['actual']['active_profile_index']=1
    run=Mock(return_value=SimpleNamespace(returncode=0,stdout=json.dumps(data)))
    if bad=='timeout':
        import subprocess
        run.side_effect=subprocess.TimeoutExpired('private',52)
    monkeypatch.setattr('pcc.drivers.pulsar_performance.subprocess.run',run)
    if bad:
        with pytest.raises(PerformanceUnavailable):apply_performance(PerformanceApplyRequest.model_validate(body))
    else:assert apply_performance(PerformanceApplyRequest.model_validate(body)).stages[0].x==800
    run.assert_called_once()
    args,kwargs=run.call_args
    assert args[0][1:]==['-m','pcc.diagnostics.pulsar_performance_apply','--apply']
    assert kwargs['timeout']==52 and json.loads(kwargs['input'])==body and 'shell' not in kwargs

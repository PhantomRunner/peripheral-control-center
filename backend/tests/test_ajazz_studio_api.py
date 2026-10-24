import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc.drivers import registry
from pcc.drivers.ajazz_studio import AjazzStudioAdapter
from pcc.main import app
from pcc.studio_api import get_studio_service
from pcc.studio_models import StudioApplyRequest
from pcc.studio_service import StudioService, StudioBusy

OBSERVATIONS = json.loads((Path(__file__).parent / 'fixtures/ajazz_studio_observation.json').read_text())['observations']
INTENTS = {
    'lighting': {'operation': 'lighting', 'settings': OBSERVATIONS['lighting']['result']['requested']},
    'clock': {'operation': 'clock', **OBSERVATIONS['clock']['result']['requested']},
    'standby': {'operation': 'standby', 'minutes': 5},
}
URL = '/api/devices/ajazz_ak820_pro/studio/apply'


@pytest.fixture
def api(monkeypatch):
    present = {'0c45:8009'}
    monkeypatch.setattr(registry, 'scan_usb_ids', lambda *args: present)
    adapter = Mock(validation_reference='fake-only exact-device observation')
    service = StudioService(adapter)
    app.dependency_overrides[get_studio_service] = lambda: service
    try:
        with TestClient(app, base_url='http://127.0.0.1:5173') as client:
            token = client.get('/api/session', headers={'X-PCC-Client':'web'}).json()['token']
            headers = {'Origin':'http://127.0.0.1:5173','X-PCC-Client':'web','X-PCC-Session':token}
            yield client, headers, adapter, present, service
    finally: app.dependency_overrides.clear()


@pytest.mark.parametrize('operation', INTENTS)
def test_explicit_studio_apply_reports_only_requested_intent_and_ack(api, operation):
    client, headers, adapter, _, _service = api
    intent = INTENTS[operation]
    response = client.post(URL, headers=headers, json={'intent':intent,'vendor_tools_closed':True,'allow_device_memory_writes':True})
    assert response.status_code == 200
    assert response.json() == {'status':'acknowledged','device_id':'ajazz_ak820_pro','requested':intent,'actual_settings':None,'persistence_verified':False}
    adapter.apply.assert_called_once()
    keyboard = client.get('/api/devices').json()['devices'][1]
    assert keyboard['battery_percent'] is keyboard['firmware_version'] is None
    assert keyboard['studio_capabilities']['clock_write'] is True


def test_session_consents_receiver_mode_and_bad_semantics_precede_io(api):
    client, headers, adapter, present, _service = api
    body = {'intent':INTENTS['lighting'],'vendor_tools_closed':True,'allow_device_memory_writes':True}
    assert client.post(URL, json=body).status_code == 403
    for flags in ({}, {'vendor_tools_closed':True}, {'allow_device_memory_writes':True}):
        assert client.post(URL, headers=headers, json={'intent':INTENTS['lighting'],**flags}).status_code == 409
    assert client.post(URL, headers=headers, json={**body,'packet':'04ff'}).status_code == 422
    bad = {'intent':{'operation':'standby','minutes':True},'vendor_tools_closed':True,'allow_device_memory_writes':True}
    assert client.post(URL, headers=headers, json=bad).status_code == 422
    present.clear(); present.add('0c45:fdfd')
    assert client.post(URL, headers=headers, json=body).status_code == 409
    adapter.apply.assert_not_called()


def test_competing_reads_or_partial_failures_do_not_retry_or_disclose_paths(api):
    client, headers, adapter, _, service = api
    body = {'intent':INTENTS['standby'],'vendor_tools_closed':True,'allow_device_memory_writes':True}
    service.operation_lock.acquire()
    try: assert client.post(URL, headers=headers, json=body).status_code == 423
    finally: service.operation_lock.release()
    adapter.apply.assert_not_called()
    adapter.apply.side_effect = RuntimeError('/private/device/serial')
    response = client.post(URL, headers=headers, json=body)
    assert response.status_code == 502 and 'private' not in response.text
    adapter.apply.assert_called_once()


@pytest.mark.parametrize('operation', INTENTS)
def test_recorded_hardware_observations_validate_without_replaying_them(monkeypatch, operation):
    intent = StudioApplyRequest.model_validate({'intent':INTENTS[operation]}).intent
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(OBSERVATIONS[operation]['result'])))
    monkeypatch.setattr('pcc.drivers.ajazz_studio.subprocess.run', run)
    AjazzStudioAdapter().apply(intent)
    args, options = run.call_args
    assert args[0][1:] == ['-m','pcc.diagnostics.ajazz_studio_probe','--operation',operation,'--apply','--vendor-tools-closed','--allow-device-memory-writes']
    assert options['timeout'] == 10 and 'shell' not in options
    assert json.loads(options['input']) == INTENTS[operation]
    run.assert_called_once()


@pytest.mark.parametrize('failure', ['partial','wrong_intent','fabricated_readback','timeout','exit'])
def test_bad_child_results_are_rejected_without_retry(monkeypatch, failure):
    result = copy.deepcopy(OBSERVATIONS['lighting']['result'])
    if failure == 'partial': result['diagnostics']['feature_sets_completed'] = 3
    if failure == 'wrong_intent': result['requested']['effect'] = 'off'
    if failure == 'fabricated_readback': result['actual_settings'] = {'color':'#4080ff'}
    run = Mock(return_value=SimpleNamespace(returncode=2 if failure == 'exit' else 0, stdout=json.dumps(result)))
    if failure == 'timeout': run.side_effect = subprocess.TimeoutExpired('private',10)
    monkeypatch.setattr('pcc.drivers.ajazz_studio.subprocess.run', run)
    intent = StudioApplyRequest.model_validate({'intent':INTENTS['lighting']}).intent
    with pytest.raises(RuntimeError): AjazzStudioAdapter().apply(intent)
    run.assert_called_once()

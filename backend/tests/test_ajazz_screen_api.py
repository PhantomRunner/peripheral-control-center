import base64
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pcc.main import app
from pcc.drivers import registry
from pcc.drivers.ajazz_screen import AjazzScreenAdapter
from pcc.screen_models import ScreenIntent, ScreenApplyRequest, MAX_REQUEST_BYTES, artwork_payload, artwork_digest
from pcc.screen_jobs import ScreenJobs
from pcc.studio_service import StudioService, StudioBusy
from pcc.studio_screen_api import get_screen_jobs

FRAME = {'rgb565_base64':base64.b64encode(bytes(32768)).decode(),'delay_ms':0}
URL = '/api/devices/ajazz_ak820_pro/studio/screen/jobs'


@pytest.fixture
def api(monkeypatch):
    present = {'0c45:8009'}
    monkeypatch.setattr(registry, 'scan_usb_ids', lambda *args: present)
    control = StudioService(Mock(validation_reference='fake-control'))
    adapter = Mock(validation_reference='fake-screen')
    queued = []
    now = [0.0]
    jobs = ScreenJobs(control,adapter,executor=queued.append,clock=lambda:now[0])
    app.dependency_overrides[get_screen_jobs] = lambda:jobs
    try:
        with TestClient(app,base_url='http://127.0.0.1:5173') as client:
            token = client.get('/api/session',headers={'X-PCC-Client':'web'}).json()['token']
            headers = {'Origin':'http://127.0.0.1:5173','X-PCC-Client':'web','X-PCC-Session':token}
            yield client,headers,adapter,jobs,queued,present,now
    finally: app.dependency_overrides.clear()


def test_artwork_job_owns_keyboard_until_completion_and_status_performs_no_io(api):
    client,headers,adapter,jobs,queued,_,now = api
    request = {'frames':[FRAME],'vendor_tools_closed':True,'allow_device_memory_writes':True}
    response = client.post(URL,headers=headers,json=request)
    assert response.status_code == 202
    job = response.json(); assert job['status'] == 'running' and job['total_blocks'] == 9
    assert client.post(URL,headers=headers,json=request).status_code == 423
    adapter.apply.assert_not_called()
    for _ in range(3): assert client.get(URL+'/'+job['id'],headers=headers).json()['status'] == 'running'
    adapter.apply.assert_not_called()
    queued.pop()()
    result = client.get(URL+'/'+job['id'],headers=headers).json()
    assert result['status'] == 'transfer_completed' and result['actual_settings'] is None and result['persistence_verified'] is False
    adapter.apply.assert_called_once()
    now[0] = 601
    assert client.get(URL+'/'+job['id'],headers=headers).status_code == 404


def test_job_requires_session_consents_wired_presence_and_bounded_valid_artwork(api):
    client,headers,adapter,_jobs,queued,present,_ = api
    body = {'frames':[FRAME],'vendor_tools_closed':True,'allow_device_memory_writes':True}
    assert client.post(URL,json=body).status_code == 403
    assert client.post(URL,headers=headers,json={'frames':[FRAME]}).status_code == 409
    assert client.post(URL,headers=headers,json={**body,'packet':'arbitrary'}).status_code == 422
    assert client.post(URL,headers=headers,json={**body,'frames':[{**FRAME,'rgb565_base64':'short'}]}).status_code == 422
    assert client.post(URL,headers={**headers,'Content-Type':'application/json'},content=b' '*(MAX_REQUEST_BYTES+1)).status_code == 413
    present.clear(); present.add('0c45:fdfd')
    assert client.post(URL,headers=headers,json=body).status_code == 409
    assert not queued; adapter.apply.assert_not_called()


def test_failed_job_releases_owner_redacts_error_and_is_not_replayed(api):
    client,headers,adapter,_jobs,queued,_,_ = api
    body = {'frames':[FRAME],'vendor_tools_closed':True,'allow_device_memory_writes':True}
    job = client.post(URL,headers=headers,json=body).json()
    adapter.apply.side_effect = RuntimeError('/private/serial')
    queued.pop()()
    response = client.get(URL+'/'+job['id'],headers=headers)
    assert response.json()['status'] == 'failed' and 'private' not in response.text
    for _ in range(2): client.get(URL+'/'+job['id'],headers=headers)
    adapter.apply.assert_called_once()
    assert client.post(URL,headers=headers,json=body).status_code == 202


def test_job_metadata_is_origin_bound(api):
    client,headers,_adapter,_jobs,_queued,_,_ = api
    job = client.post(URL,headers=headers,json={'frames':[FRAME],'vendor_tools_closed':True,'allow_device_memory_writes':True}).json()
    assert client.get(URL+'/'+job['id']).status_code == 403
    assert client.get(URL+'/'+job['id'],headers={'X-PCC-Client':'web','Host':'127.0.0.1:5181'}).status_code == 404


def test_multiframe_header_timing_bounds_and_maximum_transfer_size():
    intent = ScreenIntent(frames=[{**FRAME,'delay_ms':101},{**FRAME,'delay_ms':1000}])
    payload = artwork_payload(intent)
    assert payload[:4] == bytes((2,51,255,255))
    maximum = ScreenIntent(frames=[{**FRAME,'delay_ms':100}]*120)
    assert len(artwork_payload(maximum)) == 961*4096
    with pytest.raises(ValidationError): ScreenIntent(frames=[{**FRAME,'delay_ms':100}]*121)
    with pytest.raises(ValidationError): ScreenIntent(frames=[FRAME,FRAME])


def completed(intent):
    chunks = len(artwork_payload(intent))//4096
    return {'status':'screen_transfer_completed_visual_check_required','operation':'screen','usb_id':'0c45:8009',
            'requested':{'frame_count':len(intent.frames),'payload_sha256':artwork_digest(intent)},'actual_settings':None,
            'persistence_verified':False,'data_receipt_semantics_verified':False,
            'diagnostics':{'phase':'save','feature_sets_attempted':3,'feature_sets_completed':3,'feature_gets_attempted':4,
                           'data_outputs_attempted':chunks,'data_outputs_completed':chunks,'data_receipts':chunks,
                           'data_receipt_semantics_verified':False,'data_reply_length':64}}


def test_child_only_accepts_semantic_pixels_with_a_fixed_bound_and_no_shell(monkeypatch):
    intent = ScreenIntent(frames=[FRAME])
    run = Mock(return_value=SimpleNamespace(returncode=0,stdout=json.dumps(completed(intent))))
    monkeypatch.setattr('pcc.drivers.ajazz_screen.subprocess.run',run)
    AjazzScreenAdapter().apply(intent)
    args, options = run.call_args
    assert args[0][1:] == ['-m','pcc.diagnostics.ajazz_screen_apply','--apply','--vendor-tools-closed','--allow-device-memory-writes']
    assert options['timeout'] == 305 and 'shell' not in options
    assert set(json.loads(options['input'])) == {'frames'}
    run.assert_called_once()


@pytest.mark.parametrize('failure',['partial','digest','readback','receipt'])
def test_partial_or_wrong_transfer_results_cannot_report_success(monkeypatch,failure):
    intent = ScreenIntent(frames=[FRAME]); result=completed(intent)
    if failure == 'partial': result['diagnostics']['data_outputs_completed']=8
    if failure == 'digest': result['requested']['payload_sha256']='0'*64
    if failure == 'readback': result['actual_settings']={'screen':'fake'}
    if failure == 'receipt': result['data_receipt_semantics_verified']=True
    run=Mock(return_value=SimpleNamespace(returncode=0,stdout=json.dumps(result)))
    monkeypatch.setattr('pcc.drivers.ajazz_screen.subprocess.run',run)
    with pytest.raises(RuntimeError): AjazzScreenAdapter().apply(intent)
    run.assert_called_once()

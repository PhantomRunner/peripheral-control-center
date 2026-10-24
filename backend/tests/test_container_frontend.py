from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from pcc import container
from pcc.frontend import mount_frontend
from pcc.main import app
from pcc.profile_api import get_profile_store
from pcc.profiles import ProfileStore


@pytest.fixture
def packaged_api(tmp_path):
    bundle=tmp_path/'bundle'
    (bundle/'assets').mkdir(parents=True)
    (bundle/'index.html').write_text('<!doctype html><title>PCC packaged</title><div id="root"></div>')
    (bundle/'assets/app-test.js').write_text('export const pcc = true;')
    (bundle/'third-party-notices.txt').write_text('MIT notices')
    (tmp_path/'secret.txt').write_text('outside bundle')
    original=list(app.router.routes)
    mount_frontend(app,str(bundle))
    app.dependency_overrides[get_profile_store]=lambda:ProfileStore(tmp_path/'data')
    try:
        with TestClient(app,base_url='http://127.0.0.1:8080') as client:
            yield client
    finally:
        app.router.routes[:]=original
        app.dependency_overrides.clear()


def test_packaged_ui_assets_and_api_share_origin_without_html_api_fallback(packaged_api):
    client=packaged_api
    response=client.get('/')
    assert response.status_code==200 and 'PCC packaged' in response.text
    assert response.headers['cache-control']=='no-cache'
    assert response.headers['x-content-type-options']=='nosniff'
    assert 'javascript' in client.get('/assets/app-test.js').headers['content-type']
    assert client.get('/third-party-notices.txt').text=='MIT notices'
    assert client.get('/api/health').json()=={'status':'ok'}
    assert client.get('/api/missing').status_code==404
    assert client.get('/%2e%2e/secret.txt').status_code==404
    assert client.get('/.env').status_code==404


def test_packaged_origin_and_session_protection_still_guard_profile_writes(packaged_api):
    client=packaged_api
    draft={'name':'Container profile','device_id':'pulsar_susanto_x','settings':{'kind':'mouse','dpi':800,'polling_rate_hz':None}}
    assert client.post('/api/profiles',json=draft).status_code==403
    token=client.get('/api/session',headers={'X-PCC-Client':'web'}).json()['token']
    headers={'Origin':'http://127.0.0.1:8080','X-PCC-Client':'web','X-PCC-Session':token}
    assert client.post('/api/profiles',headers={**headers,'Origin':'http://foreign.example'},json=draft).status_code==403
    assert client.post('/api/profiles',headers=headers,json=draft).status_code==201
    assert client.get('/api/profiles',headers={'X-PCC-Client':'web'}).json()['profiles'][0]['name']=='Container profile'


def test_static_bundle_is_opt_in_and_missing_build_fails_early(tmp_path):
    from fastapi import FastAPI
    local=FastAPI()
    before=list(local.routes)
    mount_frontend(local,None)
    assert local.routes==before
    with pytest.raises(RuntimeError,match='Rebuild'):
        mount_frontend(local,str(tmp_path))


def test_explicit_data_home_does_not_require_container_passwd_entry(monkeypatch,tmp_path):
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path))
    monkeypatch.setattr(Path,'home',Mock(side_effect=RuntimeError('No passwd entry')))
    assert ProfileStore().directory==tmp_path/'pcc'


def test_container_stays_non_root_loopback_only_and_single_worker(monkeypatch):
    run=Mock()
    monkeypatch.setattr(container.uvicorn,'run',run)
    monkeypatch.setattr(container.os,'umask',Mock())
    monkeypatch.setattr(container.os,'geteuid',lambda:1000)
    monkeypatch.setenv('PCC_PORT','8085')
    container.main()
    assert run.call_args.kwargs=={'host':'127.0.0.1','port':8085,'workers':1,'proxy_headers':False,'access_log':False}
    monkeypatch.setattr(container.os,'geteuid',lambda:0)
    with pytest.raises(SystemExit,match='non-root'):
        container.main()
    run.assert_called_once()


@pytest.mark.parametrize('port',['0','80','65536','invalid'])
def test_container_rejects_invalid_or_privileged_ports(monkeypatch,port):
    monkeypatch.setattr(container.os,'geteuid',lambda:1000)
    monkeypatch.setenv('PCC_PORT',port)
    with pytest.raises(SystemExit,match='PCC_PORT'):
        container.main()

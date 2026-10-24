import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('node,message',[('/dev/hidraw999999','targeted user permissions'),('/etc/passwd','Invalid HID mapping')])
def test_host_launcher_rejects_missing_access_or_invalid_mapping_before_up(tmp_path,node,message):
    repo=tmp_path/'checkout'
    (repo/'scripts').mkdir(parents=True)
    script=Path(__file__).resolve().parents[2]/'scripts/pcc-docker'
    shutil.copyfile(script,repo/'scripts/pcc-docker')
    binaries=tmp_path/'bin'
    binaries.mkdir()
    stubs={
        'id':'case "$1" in -u|-g) echo 1000 ;; esac\n',
        'stat':'case "$2" in %u) echo 1000 ;; %a) echo 700 ;; esac\n',
        'docker':'''printf '%s\\n' "$*" >> "$PCC_TEST_LOG"
case "$1:$2" in
  context:inspect) echo unix:///fake-docker.sock ;;
  info:--format) echo '["name=seccomp"]' ;;
  compose:build) exit 0 ;;
  run:*) printf '%s\\n' "$PCC_TEST_NODE" > .pcc-docker/hid-nodes ;;
  *) exit 93 ;;
esac
''',
    }
    for name,body in stubs.items():
        path=binaries/name
        path.write_text('#!/bin/sh\n'+body)
        path.chmod(0o700)
    env={**os.environ,'PATH':str(binaries)+os.pathsep+os.environ['PATH'],
         'XDG_RUNTIME_DIR':str(tmp_path/'runtime'),'PCC_TEST_NODE':node,'PCC_TEST_LOG':str(tmp_path/'calls')}
    env.pop('DOCKER_HOST',None)
    env.pop('DOCKER_CONTEXT',None)
    # conftest forbids real diagnostic subprocesses; this is an isolated shell
    # launcher whose Docker/id/stat commands are fakes and no HID node exists.
    process=subprocess.Popen(['/bin/sh',str(repo/'scripts/pcc-docker')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    stdout,stderr=process.communicate(timeout=5)
    assert process.returncode==1 and message in stderr
    calls=(tmp_path/'calls').read_text()
    assert 'compose build pcc' in calls and 'run --rm' in calls
    assert 'compose -f' not in calls
    assert node not in stderr

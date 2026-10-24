import os
import stat
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pcc import container_devices as devices


@pytest.fixture
def topology(tmp_path,monkeypatch):
    root=tmp_path/'class'
    root.mkdir()
    dev=tmp_path/'dev'
    nodes={}
    def add(name,vid='3710',pid='5406',interface='01',bus=1,number=2,descriptor='known'):
        usb=tmp_path/f'usb-{name}'
        port=usb/f'interface-{interface}'
        hid=port/'hid-device'
        hid.mkdir(parents=True)
        for filename,value in [('idVendor',vid),('idProduct',pid),('busnum',str(bus)),('devnum',str(number))]:
            (usb/filename).write_text(value)
        (port/'bInterfaceNumber').write_text(interface)
        (hid/'report_descriptor').write_text(descriptor)
        link=root/name
        link.mkdir()
        (link/'device').symlink_to(hid)
        nodes[dev/name]=SimpleNamespace(st_mode=stat.S_IFCHR|0o660,st_rdev=os.makedev(243,int(name[6:])))
        nodes[dev/f'bus/usb/{bus:03}/{number:03}']=SimpleNamespace(st_mode=stat.S_IFCHR|0o600,st_rdev=os.makedev(189,number))
        return hid
    def digest(path):
        if path.read_text()!='known':return 'unknown'
        interface=path.parent.parent
        usb=interface.parent
        return devices.SUPPORTED.get(((usb/'idVendor').read_text(),(usb/'idProduct').read_text(),(interface/'bInterfaceNumber').read_text()),'unknown')
    monkeypatch.setattr(devices,'descriptor_digest',digest)
    return root,dev,nodes,add


def config(topology):
    root,dev,nodes,_=topology
    return devices.hardware_override(1000,'/run/user/1000/pcc-1000-locks',sys_root=root,dev_root=dev,
        inspect_node=lambda p:nodes[p])['services']['pcc']


def test_selects_only_exact_control_interfaces_and_exact_cgroup_minors(topology):
    _,_,_,add=topology
    add('hidraw0')
    add('hidraw1',vid='0c45',pid='8009',interface='03',number=3)
    add('hidraw2',vid='0c45',pid='8009',interface='02',number=3)
    add('hidraw3',interface='00')
    add('hidraw4',vid='0c45',pid='fdfd',interface='03')
    add('hidraw5',vid='1234',pid='5678')
    result=config(topology)
    targets={v['target'] for v in result['volumes']}
    assert targets=={'/dev/hidraw0','/dev/hidraw1','/dev/hidraw2','/dev/bus/usb/001/002','/dev/bus/usb/001/003','/tmp/pcc-1000-locks'}
    assert set(result['device_cgroup_rules'])=={'c 243:0 rw','c 243:1 rw','c 243:2 rw','c 189:2 r','c 189:3 r'}
    assert result['pid']=='host'
    assert not any('*' in rule or 'm' in rule for rule in result['device_cgroup_rules'])
    assert all(v['bind']['create_host_path'] is False for v in result['volumes'])
    assert all(v['read_only'] is True for v in result['volumes'] if '/bus/usb/' in v['target'])


def test_no_devices_maps_only_shared_private_lock_directory(topology):
    result=config(topology)
    assert result['device_cgroup_rules']==[] and len(result['volumes'])==1


def test_unknown_descriptor_and_duplicate_targets_fail_closed(topology):
    _,_,_,add=topology
    hid=add('hidraw0',descriptor='changed')
    with pytest.raises(devices.DeviceMappingError,match='descriptor'):config(topology)
    (hid/'report_descriptor').write_text('known')
    add('hidraw1')
    with pytest.raises(devices.DeviceMappingError,match='Multiple'):config(topology)


def test_non_character_nodes_are_rejected_without_permissions_changes(topology):
    root,dev,nodes,add=topology
    add('hidraw0')
    nodes[dev/'hidraw0']=SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_rdev=0)
    with pytest.raises(devices.DeviceMappingError,match='node changed'):config(topology)


@pytest.mark.parametrize('uid,path',[(0,'/run/user/0/pcc-0-locks'),(1000,'/tmp'),(1000,'relative/pcc-1000-locks')])
def test_root_or_broad_or_relative_lock_mount_is_rejected(uid,path):
    with pytest.raises(devices.DeviceMappingError):devices.hardware_override(uid,path)


def test_invalid_usb_address_cannot_become_a_mount_path(topology):
    _,_,_,add=topology
    add('hidraw0',bus=1000)
    with pytest.raises(devices.DeviceMappingError,match='address'):config(topology)


def test_helper_writes_private_host_acl_checklist_without_device_access_checks(topology,tmp_path,monkeypatch):
    _,_,_,add=topology
    add('hidraw0')
    def forbidden(*args):
        raise AssertionError('Metadata helper must not ask cgroups for device access')
    monkeypatch.setattr(devices.os,'access',forbidden)
    result={'services':{'pcc':config(topology)}}
    devices.write_override(result,tmp_path)
    assert json.loads((tmp_path/'compose.hardware.json').read_text())==result
    assert (tmp_path/'hid-nodes').read_text()=='/dev/hidraw0\n'
    assert stat.S_IMODE((tmp_path/'compose.hardware.json').stat().st_mode)==0o600
    assert stat.S_IMODE((tmp_path/'hid-nodes').stat().st_mode)==0o600

"""Select exact container device mounts using cached metadata only, never HID IO.

Run this short-lived helper without device cgroup permissions. Its view of host
/dev is read-only and is used only for lstat/access checks; the app receives only
the selected nodes, preserving host ACLs through bind mounts.
"""

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path

SUPPORTED = {
    ('3710','5406','01'): '655f29b1550cd7903311346991d3a5dc54988ab7326ac30cdd6284a784489c5e',
    ('0c45','8009','03'): 'a28e1d82c9261a181f75ab65ee28dc2e66e003e6d9a5c337df3a124bb8e62c7f',
    ('0c45','8009','02'): '949444322d886b5e812e965ab489434f765546581bfae8fb72df5185c0cb1169',
}


class DeviceMappingError(Exception):
    pass


def descriptor_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def device_mounts(sys_root: Path = Path('/sys/class/hidraw'), dev_root: Path = Path('/host-dev'), *,
                  inspect_node: Callable = os.lstat) -> tuple[list[dict], list[str]]:
    mounts: dict[str, dict] = {}
    rules: set[str] = set()
    selected: set[tuple[str,str,str]] = set()

    def add(relative: str, *, writable: bool) -> None:
        info = inspect_node(dev_root / relative)
        if not stat.S_ISCHR(info.st_mode):
            raise DeviceMappingError('A matching device node changed; reconnect and retry.')
        # Device cgroup restrictions also affect access(), so this metadata-only
        # helper must not use it to infer host ACLs. Launcher checks host R/W.
        target = '/dev/' + relative
        mounts[target] = {'type':'bind','source':target,'target':target,'read_only':not writable,
                          'bind':{'create_host_path':False}}
        rules.add(f'c {os.major(info.st_rdev)}:{os.minor(info.st_rdev)} {"rw" if writable else "r"}')

    if not sys_root.is_dir():
        return [], []
    for entry in sorted(sys_root.iterdir()):
        if re.fullmatch(r'hidraw[0-9]+', entry.name) is None:
            continue
        try:
            hid = (entry / 'device').resolve(strict=True)
            interface = next((p for p in hid.parents if (p / 'bInterfaceNumber').is_file()), None)
            if interface is None:
                continue
            usb = interface.parent
            signature = tuple((p.read_text().strip().lower()) for p in
                              (usb/'idVendor',usb/'idProduct',interface/'bInterfaceNumber'))
            if signature not in SUPPORTED:
                continue
            if descriptor_digest(hid/'report_descriptor') != SUPPORTED[signature]:
                raise DeviceMappingError('A matching USB interface has an unrecognised report descriptor.')
            if signature in selected:
                raise DeviceMappingError('Multiple matching control interfaces found; keep one target of each model connected.')
            bus, number = int((usb/'busnum').read_text()), int((usb/'devnum').read_text())
            if not 1 <= bus <= 999 or not 1 <= number <= 999:
                raise DeviceMappingError('Invalid cached USB address.')
            add(entry.name,writable=True)
            # Diagnostics stat usbfs for identity/competing-handle checks; they
            # perform IO through hidraw only. No writable USB bus is exposed.
            add(f'bus/usb/{bus:03}/{number:03}',writable=False)
            selected.add(signature)
        except FileNotFoundError:
            raise DeviceMappingError('A device disappeared during discovery; reconnect and retry.') from None
        except (OSError,ValueError):
            raise DeviceMappingError('Device metadata is unavailable; check the connected targets.') from None
    return list(mounts.values()), sorted(rules)


def hardware_override(uid: int, host_lock: str, **discovery) -> dict:
    if type(uid) is not int or uid <= 0 or not Path(host_lock).is_absolute() or Path(host_lock).name != f'pcc-{uid}-locks':
        raise DeviceMappingError('A non-root host UID and its private PCC lock directory are required.')
    mounts, rules = device_mounts(**discovery)
    mounts.append({'type':'bind','source':host_lock,'target':f'/tmp/pcc-{uid}-locks','read_only':False,
                   'bind':{'create_host_path':False}})
    # Host PID visibility retains the existing competing-tools checks. Exact
    # bind mounts retain host ACLs that --device-created nodes can lose.
    return {'services':{'pcc':{'pid':'host','volumes':mounts,'device_cgroup_rules':rules}}}


def main() -> None:
    try:
        result = hardware_override(os.getuid(), os.environ.get('PCC_HOST_LOCK_DIR',''))
        write_override(result,Path('/output'))
        volumes = result['services']['pcc']['volumes']
        print(json.dumps({'mapped_hid_interfaces':sum(v['target'].startswith('/dev/hidraw') for v in volumes),
                          'device_io':False}))
    except (DeviceMappingError,OSError) as error:
        detail = str(error) if isinstance(error,DeviceMappingError) else 'Container configuration could not be written.'
        raise SystemExit(detail) from None


def write_override(result: dict, output: Path) -> None:
    hid_nodes = [v['source'] for v in result['services']['pcc']['volumes'] if v['target'].startswith('/dev/hidraw')]
    for name, body in [('compose.hardware.json',json.dumps(result,indent=2)+'\n'),
                       ('hid-nodes',''.join(node+'\n' for node in hid_nodes))]:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=output,delete=False) as target:
            temporary=Path(target.name)
            target.write(body)
        try:
            temporary.replace(output/name)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()

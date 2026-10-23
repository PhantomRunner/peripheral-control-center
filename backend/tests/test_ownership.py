import hashlib
from pathlib import Path

import pytest

from pcc.ownership import DeviceBusyError, DeviceOwnership, OwnershipUnavailableError


def test_independent_managers_cannot_claim_the_same_device(tmp_path: Path):
    first = DeviceOwnership(tmp_path / "locks")
    second = DeviceOwnership(tmp_path / "locks")
    with first.claim("pulsar_susanto_x"):
        with pytest.raises(DeviceBusyError):
            with second.claim("pulsar_susanto_x"):
                pytest.fail("Duplicate ownership")
        with second.claim("ajazz_ak820_pro"):
            pass
    with second.claim("pulsar_susanto_x"):
        pass


def test_exceptions_release_ownership(tmp_path: Path):
    owner = DeviceOwnership(tmp_path / "locks")
    with pytest.raises(ValueError):
        with owner.claim("mouse"):
            raise ValueError("fake operation failed")
    with owner.claim("mouse"):
        pass


def test_insecure_directory_and_symlink_are_rejected(tmp_path: Path):
    directory = tmp_path / "locks"
    directory.mkdir(mode=0o755)
    with pytest.raises(OwnershipUnavailableError, match="^Device ownership is unavailable.$"):
        with DeviceOwnership(directory).claim("mouse"):
            pass
    link = tmp_path / "alias"
    link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(OwnershipUnavailableError):
        with DeviceOwnership(link).claim("mouse"):
            pass


def test_lock_symlink_does_not_touch_target(tmp_path: Path):
    directory = tmp_path / "locks"
    directory.mkdir(mode=0o700)
    target = tmp_path / "private"
    target.write_text("unchanged")
    name = hashlib.sha256(b"mouse").hexdigest() + ".lock"
    (directory / name).symlink_to(target)
    with pytest.raises(OwnershipUnavailableError):
        with DeviceOwnership(directory).claim("mouse"):
            pass
    assert target.read_text() == "unchanged"

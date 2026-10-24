"""Private, atomic local software profiles; saving never applies settings."""

import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import Field, ValidationError, model_validator

from .ownership import DeviceBusyError, DeviceOwnership, OwnershipUnavailableError
from .settings import ProfileDraft, ProfileUpdate, SoftwareProfile, StrictModel


class ProfileNotFoundError(Exception):
    pass


class ProfileConflictError(Exception):
    pass


class ProfileStorageError(Exception):
    pass


class _ProfileFile(StrictModel):
    schema_version: Literal[1] = 1
    profiles: list[SoftwareProfile] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len({profile.id for profile in self.profiles}) != len(self.profiles):
            raise ValueError("Duplicate profile IDs.")
        return self


class ProfileStore:
    def __init__(self, directory: Path | None = None) -> None:
        configured_home = os.environ.get('XDG_DATA_HOME')
        data_home = Path(configured_home) if configured_home else Path.home() / '.local' / 'share'
        self.directory = directory if directory is not None else data_home / "pcc"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = self.directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ProfileStorageError("Local profile storage is unavailable.")
            with DeviceOwnership(self.directory / "locks").claim("software_profiles"):
                yield
        except DeviceBusyError:
            raise ProfileConflictError("Profiles are busy; reload and retry.") from None
        except (OSError, UnicodeError, ValidationError, OwnershipUnavailableError):
            raise ProfileStorageError("Local profile storage is unavailable.") from None

    def _read(self) -> list[SoftwareProfile]:
        try:
            descriptor = os.open(self.directory / "profiles.json", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return []
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ProfileStorageError("Local profile storage is unavailable.")
            data = source.read(262145)
            if len(data) > 262144:
                raise ProfileStorageError("Local profile storage is unavailable.")
        return _ProfileFile.model_validate_json(data).profiles

    def _write(self, profiles: list[SoftwareProfile]) -> None:
        data = _ProfileFile(profiles=profiles).model_dump_json()
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, delete=False) as target:
                temporary = Path(target.name)
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.directory / "profiles.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def list(self) -> list[SoftwareProfile]:
        with self._locked():
            return self._read()

    def get(self, profile_id: str) -> SoftwareProfile:
        for profile in self.list():
            if profile.id == profile_id:
                return profile
        raise ProfileNotFoundError("Profile not found.")

    def create(self, draft: ProfileDraft) -> SoftwareProfile:
        with self._locked():
            profiles = self._read()
            if len(profiles) >= 100:
                raise ProfileConflictError("The local limit of 100 profiles has been reached.")
            profile = SoftwareProfile(**draft.model_dump(), id=uuid4().hex, revision=1)
            self._write([*profiles, profile])
            return profile

    def update(self, profile_id: str, draft: ProfileUpdate) -> SoftwareProfile:
        with self._locked():
            profiles = self._read()
            for index, old in enumerate(profiles):
                if old.id != profile_id:
                    continue
                if old.revision != draft.revision or old.device_id != draft.device_id:
                    raise ProfileConflictError("Profile changed; reload before editing.")
                profile = SoftwareProfile(**draft.model_dump(exclude={"revision"}), id=profile_id, revision=old.revision + 1)
                profiles[index] = profile
                self._write(profiles)
                return profile
        raise ProfileNotFoundError("Profile not found.")

    def delete(self, profile_id: str, revision: int) -> None:
        with self._locked():
            profiles = self._read()
            old = next((profile for profile in profiles if profile.id == profile_id), None)
            if old is None:
                raise ProfileNotFoundError("Profile not found.")
            if old.revision != revision:
                raise ProfileConflictError("Profile changed; reload before deleting.")
            self._write([profile for profile in profiles if profile.id != profile_id])

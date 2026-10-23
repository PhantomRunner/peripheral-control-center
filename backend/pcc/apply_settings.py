"""Explicit settings operations through separately validated adapters only.

The default registry is empty. No live transport or protocol writer is present.
"""

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Protocol

from .ownership import DeviceOwnership
from .settings import DeviceId, MouseSettings, SettingsIntent, StrictModel


class SettingsUnavailableError(Exception):
    pass


class InvalidSettingsError(Exception):
    pass


class SettingsVerificationError(Exception):
    pass


class SettingsOperationError(Exception):
    pass


class SettingsSession(Protocol):
    def write_dpi(self, dpi: int) -> None: ...
    def read_dpi(self) -> int | None: ...


class ValidatedSettingsAdapter(Protocol):
    validation_reference: str

    def validate_dpi(self, dpi: int) -> None:
        """Reject unsupported values before opening any hardware handle."""
        ...

    def session(self) -> AbstractContextManager[SettingsSession]:
        """Verify exact-device identity and external-tool ownership before IO.

        Opening and closing must not switch profiles or persist settings.
        No real implementation is registered until hardware validation exists.
        """
        ...


class ApplyRequest(StrictModel):
    settings: SettingsIntent


class SettingsService:
    def __init__(self, adapters: Mapping[str, ValidatedSettingsAdapter] | None = None, ownership: DeviceOwnership | None = None) -> None:
        self._adapters = dict(adapters or {})
        self._ownership = ownership if ownership is not None else DeviceOwnership()

    def apply(self, device_id: DeviceId, desired: SettingsIntent) -> MouseSettings:
        if device_id != "pulsar_susanto_x" or not isinstance(desired, MouseSettings) or desired.dpi is None or desired.polling_rate_hz is not None:
            raise SettingsUnavailableError("This settings operation is unavailable.")
        adapter = self._adapters.get(device_id)
        if adapter is None or not adapter.validation_reference:
            raise SettingsUnavailableError("No validated settings adapter is enabled for this device.")
        try:
            adapter.validate_dpi(desired.dpi)
        except ValueError:
            raise InvalidSettingsError("DPI is not supported by this adapter.") from None
        with self._ownership.claim(device_id):
            try:
                with adapter.session() as session:
                    session.write_dpi(desired.dpi)
                    actual = session.read_dpi()
                    if type(actual) is not int or actual != desired.dpi:
                        raise SettingsVerificationError("DPI write could not be verified. Device state may have changed.")
                    return MouseSettings(kind="mouse", dpi=actual)
            except (OSError, RuntimeError):
                raise SettingsOperationError("Device operation failed. State may have changed; check it before retrying.") from None

"""Extension point for device adapters; no hardware commands yet."""

from typing import Protocol

from pcc.models import DeviceSummary


class ReadOnlyDeviceAdapter(Protocol):
    """An adapter must distinguish enumeration from real hardware readback."""

    def get_summary(self) -> DeviceSummary: ...

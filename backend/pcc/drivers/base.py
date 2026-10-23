"""Extension point for device adapters; no hardware commands yet."""

from typing import AbstractSet, Protocol

from pcc.models import DeviceSummary


class ReadOnlyDeviceAdapter(Protocol):
    """An adapter must distinguish enumeration from real hardware readback."""

    def get_summary(self, present_usb_ids: AbstractSet[str]) -> DeviceSummary:
        """Describe an enumeration snapshot without opening hardware interfaces."""
        ...

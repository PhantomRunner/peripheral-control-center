"""Map a single read-only USB enumeration snapshot through registered adapters."""

from collections.abc import Iterable
from pathlib import Path
from typing import AbstractSet

from pcc.models import DeviceSummary
from pcc.scanner import scan_usb_ids

from .ajazz import AjazzAdapter
from .base import ReadOnlyDeviceAdapter
from .pulsar import PulsarAdapter


class AdapterRegistry:
    def __init__(self, adapters: Iterable[ReadOnlyDeviceAdapter]) -> None:
        self._adapters = tuple(adapters)

    def get_summaries(self, present_usb_ids: AbstractSet[str]) -> list[DeviceSummary]:
        snapshot = frozenset(present_usb_ids)
        return [adapter.get_summary(snapshot) for adapter in self._adapters]


DEFAULT_REGISTRY = AdapterRegistry((PulsarAdapter(), AjazzAdapter()))


def discover_devices(root: Path = Path("/sys/bus/usb/devices")) -> list[DeviceSummary]:
    return DEFAULT_REGISTRY.get_summaries(scan_usb_ids(root))

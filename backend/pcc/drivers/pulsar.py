"""Susanto-X discovery and separately validated explicit operation metadata."""

from typing import AbstractSet

from pcc.models import DeviceCapabilities, DeviceConnection, DeviceSummary, MouseWriteOptions
from .protocols.pulsar_settings import DPI_RECORDS, POLLING_RECORDS
from pcc.performance_support import validated_capabilities


class PulsarAdapter:
    RECEIVER_USB_ID = "3710:5406"

    def get_summary(self, present_usb_ids: AbstractSet[str]) -> DeviceSummary:
        receiver = self.RECEIVER_USB_ID in present_usb_ids
        return DeviceSummary(
            id="pulsar_susanto_x",
            name="Pulsar Susanto-X",
            kind="mouse",
            status="receiver_detected" if receiver else "offline",
            connected_usb_ids=[self.RECEIVER_USB_ID] if receiver else [],
            connection=DeviceConnection(receiver_usb_present=receiver),
            capabilities=DeviceCapabilities(battery_read=True, firmware_read=True, dpi_read=True, polling_rate_read=True, settings_write=True),
            driver_state="read_write",
            write_options=MouseWriteOptions(dpi=list(DPI_RECORDS), polling_rate_hz=list(POLLING_RECORDS)),
            performance_capabilities=validated_capabilities(),
            note=(
                "8K receiver detected. Hardware reads require explicit action or opt-in battery polling; wireless link is not verified."
                if receiver else "8K receiver not detected."
            ),
        )

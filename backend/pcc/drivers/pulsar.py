"""Susanto-X discovery with explicit battery/firmware read support; no writes."""

from typing import AbstractSet

from pcc.models import DeviceCapabilities, DeviceConnection, DeviceSummary


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
            capabilities=DeviceCapabilities(battery_read=True, firmware_read=True),
            driver_state="read_only",
            note=(
                "8K receiver detected. Battery and firmware can be read manually; wireless link is not verified."
                if receiver else "8K receiver not detected."
            ),
        )

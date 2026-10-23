"""AJAZZ AK820 Pro USB presence only; no verified wireless link or HID reads."""

from typing import AbstractSet

from pcc.models import DeviceSummary


class AjazzAdapter:
    WIRED_USB_ID = "0c45:8009"
    RECEIVER_USB_ID = "0c45:fdfd"

    def get_summary(self, present_usb_ids: AbstractSet[str]) -> DeviceSummary:
        wired = self.WIRED_USB_ID in present_usb_ids
        receiver = self.RECEIVER_USB_ID in present_usb_ids
        return DeviceSummary(
            id="ajazz_ak820_pro",
            name="AJAZZ AK820 Pro",
            kind="keyboard",
            status=(
                "wired_detected" if wired else
                "receiver_detected" if receiver else "offline"
            ),
            connected_usb_ids=[
                usb_id for usb_id in (self.WIRED_USB_ID, self.RECEIVER_USB_ID)
                if usb_id in present_usb_ids
            ],
            note=(
                "Wired USB device detected. HID settings are not read yet."
                if wired else
                "Only the 2.4 GHz receiver is detected; this does not confirm keyboard connectivity."
                if receiver else "Keyboard and receiver not detected."
            ),
        )

"""Explicit PSSTX21 Apply, restricted to the exact tested profile/stage/values."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from pcc.diagnostics.pulsar_config_probe import ConfigHidraw, observe as read_config
from pcc.diagnostics.pulsar_probe import FixedQuery, HidrawProbe, ProbeBlocked, check_competitors, discover_target, open_probe
from .protocols.pulsar_readonly import ExpectedReply, InvalidReply, ReplyTimeout, firmware_version, receive_reply
from .protocols.pulsar_settings import dpi_packet, polling_packet, receive_write_ack


class PulsarSettingsSession:
    def __init__(self, opened: HidrawProbe):
        self._opened = opened
        opened.send_query(FixedQuery.MOUSE_FIRMWARE)
        if firmware_version(receive_reply(opened, ExpectedReply(0x12), timeout_seconds=0.5, max_reports=32)) != "3.03":
            raise ProbeBlocked("Settings writes are verified only for mouse firmware 3.03.")
        self._baseline = read_config(ConfigHidraw(opened))
        self._check_slot(self._baseline)
        self._final: dict | None = None
        self._written: set[str] = set()

    @staticmethod
    def _check_slot(snapshot: dict) -> None:
        if (snapshot["identity"] != {"cid": 87, "mid": 39, "type": 5}
                or snapshot["active_profile_index"] != 0 or snapshot["active_stage_index"] != 2
                or snapshot["stage_count"] != 5):
            raise ProbeBlocked("Only the verified onboard profile 1 / DPI stage 3 is writable.")

    def _write(self, field: str, packet: bytes) -> None:
        if field in self._written or len(self._written) >= 2:
            raise ProbeBlocked("Each setting can be written only once per Apply.")
        self._opened.target.verify_cached_identity()
        check_competitors(self._opened.numbers)
        self._written.add(field)  # An ambiguous output is never retried.
        self._final = None
        if os.write(self._opened.descriptor, packet) != len(packet):
            raise ProbeBlocked("Settings output was incomplete; state may have changed.")
        receive_write_ack(self._opened)

    def write_dpi(self, dpi: int) -> None:
        self._write("dpi", dpi_packet(dpi))

    def write_polling_rate(self, hz: int) -> None:
        self._write("polling", polling_packet(hz))

    def _snapshot(self) -> dict:
        if not self._written:
            return self._baseline
        if self._final is None:
            snapshot = read_config(ConfigHidraw(self._opened))
            self._check_slot(snapshot)
            for field, key in (("dpi", "dpi_candidate"), ("polling", "stored_polling_rate_hz_candidate")):
                if field not in self._written and snapshot["observed"][key] != self._baseline["observed"][key]:
                    raise ProbeBlocked("An unrequested setting changed during Apply.")
            self._final = snapshot
        return self._final

    def read_active_profile(self) -> int:
        return self._snapshot()["active_profile_index"]

    def read_dpi(self) -> int:
        return self._snapshot()["observed"]["dpi_candidate"]

    def read_polling_rate(self) -> int:
        return self._snapshot()["observed"]["stored_polling_rate_hz_candidate"]


class PulsarSettingsAdapter:
    validation_reference = "PSSTX21 approved 2026-10-23: 800/500 readback, 1200/1000 restored; profile 1, stage 3"
    requires_operator_confirmation = True
    session_owns_device_lock = True

    @staticmethod
    def validate_dpi(value: int) -> None:
        dpi_packet(value)

    @staticmethod
    def validate_polling_rate(value: int) -> None:
        polling_packet(value)

    @contextmanager
    def session(self) -> Iterator[PulsarSettingsSession]:
        # The service checks the explicit operator confirmation before calling.
        # open_probe holds the PCC lock throughout baseline, writes and readback.
        try:
            target = discover_target()
            with open_probe(target, vendor_tools_closed=True) as opened:
                yield PulsarSettingsSession(opened)
        except (ProbeBlocked, InvalidReply, ReplyTimeout, OSError, ValueError):
            raise RuntimeError("Pulsar operation was not confirmed; state may have changed.") from None

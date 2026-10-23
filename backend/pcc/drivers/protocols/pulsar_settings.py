"""Only settings records verified on the owner's PSSTX21 on 2026-10-23.

Nordic frame/record encoding reference (MIT): packerlschupfer/pulsar-mouse-linux
297dbf4bb933545e5a2e6f393f2c81d64bc7c347. Copyright (c) 2026 Packerlschupfer.
See LICENSE.pulsar-mouse-linux. Settings-memory writes may persist.
"""

import time

from .pulsar_readonly import ReplyTimeout, ReportSource

DPI_RECORDS = {800: bytes.fromhex("4f 4f 00 b7"), 1200: bytes.fromhex("77 77 00 67")}
POLLING_RECORDS = {500: bytes.fromhex("02 53"), 1000: bytes.fromhex("01 54")}


def _packet(address: int, payload: bytes) -> bytes:
    packet = bytearray(17)
    packet[:2] = bytes((8, 7))
    packet[3:5] = address.to_bytes(2, "big")
    packet[5] = len(payload)
    packet[6:6 + len(payload)] = payload
    packet[16] = (0x55 - sum(packet[:16])) & 255
    return bytes(packet)


def dpi_packet(value: int) -> bytes:
    if type(value) is not int or value not in DPI_RECORDS:
        raise ValueError("DPI is outside the verified write set.")
    return _packet(0x0014, DPI_RECORDS[value])


def polling_packet(value: int) -> bytes:
    if type(value) is not int or value not in POLLING_RECORDS:
        raise ValueError("Polling is outside the verified write set.")
    return _packet(0x0000, POLLING_RECORDS[value])


def receive_write_ack(source: ReportSource) -> None:
    deadline = time.monotonic() + 0.5
    for _ in range(32):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            packet = source.read_report(remaining)
        except TimeoutError:
            break
        if (len(packet) == 17 and packet[:3] == bytes((8, 7, 0))
                and packet[5] <= 10 and sum(packet) & 255 == 0x55):
            return  # Transport ACK only; the settings service requires readback.
    raise ReplyTimeout("Settings-write acknowledgement was not confirmed.")

"""Pure source-derived performance encoding; no exact-device validation implied.

Nordic record format: packerlschupfer/pulsar-mouse-linux (MIT), commit
297dbf4bb933545e5a2e6f393f2c81d64bc7c347. Copyright (c) 2026 Packerlschupfer.
Full notice: LICENSE.pulsar-mouse-linux. Bibimbap is studied, not copied.
"""

from enum import Enum

from pcc.performance_models import (ActiveStageAction, DebounceAction, LodAction, PerformanceAction,
                                    PollingAction, RotationAction, StageDpiAction, SwitchAction)
from .pulsar_readonly import InvalidReply, POLLING_CODES, Reply, complemented_value


class Register(Enum):
    POLLING = (0x0000, 2)
    STAGE_COUNT = (0x0002, 2)
    ACTIVE_STAGE = (0x0004, 2)
    LOD = (0x000A, 2)
    DPI_0 = (0x000C, 4)
    DPI_1 = (0x0010, 4)
    DPI_2 = (0x0014, 4)
    DPI_3 = (0x0018, 4)
    DPI_4 = (0x001C, 4)
    DPI_5 = (0x0020, 4)
    DEBOUNCE = (0x00A9, 2)
    MOTION_SYNC = (0x00AB, 2)
    ANGLE_SNAP = (0x00AF, 2)
    RIPPLE_CONTROL = (0x00B1, 2)
    TURBO = (0x00B5, 2)
    ROTATION = (0x00BD, 2)
    ROTATION_STATE = (0x00BF, 2)


DPI_REGISTERS = tuple(Register)[4:10]
SENSOR_REGISTERS = {
    'lod': Register.LOD, 'debounce': Register.DEBOUNCE, 'motion_sync': Register.MOTION_SYNC,
    'angle_snap': Register.ANGLE_SNAP, 'ripple_control': Register.RIPPLE_CONTROL,
    'turbo': Register.TURBO, 'rotation': Register.ROTATION,
}


def _packet(command: int, register: Register, payload: bytes = b'') -> bytes:
    if type(register) is not Register:
        raise ValueError('Only named performance registers are allowed.')
    address, length = register.value
    if command not in {7, 8} or (command == 7 and len(payload) != length) or (command == 8 and payload):
        raise ValueError('Invalid performance packet.')
    packet = bytearray(17)
    packet[:2] = bytes((8, command))
    packet[3:5] = address.to_bytes(2, 'big')
    packet[5] = length
    packet[6:6 + len(payload)] = payload
    packet[-1] = (0x55 - sum(packet[:-1])) & 255
    return bytes(packet)


def read_packet(register: Register) -> bytes:
    return _packet(8, register)


def pair(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError('Invalid configuration byte.')
    return bytes((value, (0x55 - value) & 255))


def dpi_record(value: int) -> bytes:
    if type(value) is not int or not 10 <= value <= 32000:
        raise ValueError('DPI is outside the source-derived range.')
    mode, step, base = (0, 10, 1) if value <= 10240 else (2, 50, 201) if value <= 25600 else (3, 100, 201)
    if value % step:
        raise ValueError('DPI is not representable at this granularity.')
    units = value // step - base
    page, low = divmod(units, 256)
    if not 0 <= page <= 3:
        raise ValueError('DPI is not representable.')
    nibble = mode << 2 | page
    packed = ((nibble << 2) | (nibble >> 2)) & 15
    data = bytes((low, low, packed << 4 | packed))
    return data + bytes(((0x55 - sum(data)) & 255,))


def dpi_axes(record: bytes) -> tuple[int | None, int | None]:
    if len(record) != 4 or sum(record) & 255 != 0x55:
        raise InvalidReply('Invalid DPI record checksum.')
    result = []
    for low, nibble in ((record[0], record[2] & 15), (record[1], record[2] >> 4)):
        decoded = ((nibble << 2) | (nibble >> 2)) & 15
        mode, page = decoded >> 2, decoded & 3
        parameters = {0: (10, 1), 2: (50, 201), 3: (100, 201)}
        value = None
        if mode in parameters:
            step, base = parameters[mode]
            candidate = (low + base + 256 * page) * step
            if 10 <= candidate <= 32000:
                value = candidate
        result.append(value)
    return result[0], result[1]


def decode_sensor(name: str, record: bytes, rotation_state: bytes | None = None) -> float | int | bool | None:
    if name not in SENSOR_REGISTERS:
        raise ValueError('Unknown sensor parameter.')
    # These optional records are used as the vendor support marker. Uninitialised
    # records mean unsupported, never a zero-degree reading or an enabled switch.
    if name == 'rotation' and (record == b'\xff\xff' or rotation_state == b'\xff\xff'):
        return None
    value = complemented_value(Reply(8, record))
    if name == 'lod':
        return {1: 1.0, 2: 2.0, 3: 0.7}.get(value)
    if name == 'debounce':
        return value if value <= 15 else None
    if name == 'rotation':
        if rotation_state is None or complemented_value(Reply(8, rotation_state)) not in {0, 1}:
            return None
        degrees = value - 256 if value >= 128 else value
        return degrees if -30 <= degrees <= 30 else None
    return bool(value) if value in {0, 1} else None


def write_record(action: PerformanceAction) -> tuple[Register, bytes]:
    if isinstance(action, StageDpiAction):
        return DPI_REGISTERS[action.stage_index], dpi_record(action.dpi)
    if isinstance(action, ActiveStageAction):
        return Register.ACTIVE_STAGE, pair(action.stage_index)
    if isinstance(action, PollingAction):
        return Register.POLLING, pair(next(code for code, hz in POLLING_CODES.items() if hz == action.hz))
    if isinstance(action, LodAction):
        return Register.LOD, pair({1.0: 1, 2.0: 2, 0.7: 3}[action.millimetres])
    if isinstance(action, DebounceAction):
        return Register.DEBOUNCE, pair(action.milliseconds)
    if isinstance(action, SwitchAction):
        return SENSOR_REGISTERS[action.operation], pair(int(action.enabled))
    if isinstance(action, RotationAction):
        return Register.ROTATION, pair(action.degrees & 255)
    raise ValueError('Only typed performance actions are supported.')


def write_packet(action: PerformanceAction) -> bytes:
    register, record = write_record(action)
    return _packet(7, register, record)


def action_packets(action: PerformanceAction, *, rotation_enabled: bool | None = None) -> tuple[bytes, ...]:
    packet = write_packet(action)
    if isinstance(action, RotationAction):
        if type(rotation_enabled) is not bool:
            raise ValueError('Rotation enable state is required.')
        if not rotation_enabled:
            return _packet(7, Register.ROTATION_STATE, pair(1)), packet
    return (packet,)

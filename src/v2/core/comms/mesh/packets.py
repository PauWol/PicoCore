"""
PicoCore V2 Comms Mesh Packets Utility

This module provides utility functions for the PicoCore V2 Comms Mesh module.
"""

import micropython
import os

import ustruct as struct
import ujson

from core.comms.constants import (
    BASE_HEADER_FORMAT_NO_CRC,
    BASE_HEADER_SIZE_NO_CRC,
    MESH_VERSION,
    MAX_PAYLOAD_SIZE,
    MESH_FLAG_PARTIAL_START,
    MESH_FLAG_PARTIAL_END,
    MESH_FLAG_PARTIAL,
    MESH_FLAG_GATEWAY,
    MESH_FLAG_FILE,
)
from core.comms.crc8 import append_crc8_to_bytearray, verify_crc8


def payload_conv(payload: str | bytes | bytearray):
    """
    Convert payload to bytes.
    :param payload:
    :return: bytes or generator
    """
    return payload.encode() if isinstance(payload, str) else payload


def payload_conv_iter(payload: str | bytes | bytearray):
    """
    Convert payload to bytes.
    :param payload:
    :return: bytes or generator
    """
    _p = payload.encode() if isinstance(payload, str) else payload

    for i in range(0, len(_p), MAX_PAYLOAD_SIZE):
        yield _p[i : i + MAX_PAYLOAD_SIZE]


# TODO: Make the build packet function use low level for packet building -> remove struct.pack + use memview
@micropython.native
def build_packet(
    ptype: int,
    src: int,
    dst: int,
    seq: int,
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    ttl: int,
    flags: int,
    payload: bytes,
    gateway: bool = False,
) -> bytearray:
    """
    Build a mesh packet.
    :param ptype: Payload Type
    :param src: Source Node (0-65535)
    :param dst: Destination Node (0-65535)
    :param seq: Sequence number (0-65535)
    :param ttl: Time To Live (hops)
    :param flags: Flags byte
    :param payload: Payload as bytes (0-255 bytes)
    :param gateway: If true the packet automatically adds MESH_FLAG_GATEWAY
    :return: Packet as bytearray [header+CRC8+payload]
    """
    version = MESH_VERSION
    _plen = len(payload)
    # Safety checks
    assert 0 <= version <= 255
    assert 0 <= ptype <= 255
    assert 0 <= src <= 0xFFFF  # hex for 65535
    assert 0 <= dst <= 0xFFFF
    assert 0 <= seq <= 0xFFFF
    assert 0 <= ttl <= 255
    assert 0 <= flags <= 255
    assert _plen <= 255

    if gateway:
        flags |= MESH_FLAG_GATEWAY

    # Pack header
    header = bytearray(
        struct.pack(
            BASE_HEADER_FORMAT_NO_CRC, version, ptype, src, dst, seq, ttl, flags, _plen
        )
    )

    # Append CRC8 of header
    append_crc8_to_bytearray(header)

    # append payload
    header.extend(payload)

    # Return final packet
    return header


@micropython.native
def parse_packet(
    packet: bytes,
) -> tuple[int, int, int, int, int, int, int, int, bytes] | None:
    """
    Parse a mesh packet.
    :param packet: Packet as bytes [header+CRC8+payload]
    :return: Tuple of (version, ptype, src, dst, seq, ttl, flags, plen, payload) or None if invalid
    """
    header_len = BASE_HEADER_SIZE_NO_CRC
    header_end = header_len + 1
    mv = memoryview(packet)
    # _header_crc8 = packet[: BASE_HEADER_SIZE_NO_CRC + 1] --OLD VERSION--
    # Header Sum Check
    if not verify_crc8(mv[:header_end]):
        return None

    # manual unpacking to save resources
    #   -- OLD VERSION --
    # _version, _ptype, _src, _dst, _seq, _ttl, _flags, _plen = struct.unpack(
    #         BASE_HEADER_FORMAT_NO_CRC, _header
    #     )

    _ver = mv[0]
    _ptype = mv[1]
    _src = mv[2] | (mv[3] << 8)
    _dst = mv[4] | (mv[5] << 8)
    _seq = mv[6] | (mv[7] << 8)
    _ttl = mv[8]
    _flags = mv[9]
    _plen = mv[10]

    # Checks function removed to save function call
    #     if not _checks(_version, _plen, len(_payload)):
    #         return None
    if _ver != MESH_VERSION:
        return None

    _payload = mv[header_end:]

    if _plen != len(_payload):
        return None

    return _ver, _ptype, _src, _dst, _seq, _ttl, _flags, _plen, bytes(_payload)


def chunk_packet(
    ptype: int,
    src: int,
    dst: int,
    seq: int,
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    ttl: int,
    flags: int,
    _payload: str | bytes | bytearray,
    gateway: bool,
):
    """
    Split up a payload if it exceeds MAX_PAYLOAD_SIZE in multiple messages.

    :param ptype:
    :param src:
    :param dst:
    :param seq:
    :param ttl:
    :param flags:
    :param _payload:
    :param gateway:
    :yields: the build packets
    """
    _payload = payload_conv(_payload)
    _plen = len(_payload)

    max_chunk = MAX_PAYLOAD_SIZE - 2  # -2 for chunk index

    if _plen <= max_chunk:
        yield build_packet(ptype, src, dst, seq, ttl, flags, _payload)
        return

    _chunk_count = (_plen + max_chunk - 1) // max_chunk
    mv = memoryview(_payload)

    # precompute flags
    f_mid = flags | MESH_FLAG_PARTIAL
    f_start = f_mid | MESH_FLAG_PARTIAL_START
    f_end = f_mid | MESH_FLAG_PARTIAL_END

    # reusable buffer (max size)
    _buf = bytearray(2 + max_chunk)

    _start = 0

    for i in range(_chunk_count):
        _end = _start + max_chunk
        _chunk = mv[_start:_end]
        _clen = len(_chunk)

        _buf[0] = i
        _buf[1] = _chunk_count
        _buf[2 : 2 + _clen] = _chunk

        if i == 0:
            f = f_start

        elif i == _chunk_count - 1:
            f = f_end

        else:
            f = f_mid

        yield build_packet(ptype, src, dst, seq, ttl, f, _buf[: 2 + _clen], gateway)

        _start = _end


def chunk_file(
    ptype: int,
    src: int,
    dst: int,
    seq: int,
    ttl: int,
    flags: int,
    file_path: str,
    new_name: str | None,
    gateway: bool,
):
    _size = os.stat(file_path)[6]  #
    file_name = file_path
    if new_name is not None:
        file_name = new_name

    file_name = file_name.encode("utf-8")
    l_name = len(file_name)

    max_chunk = MAX_PAYLOAD_SIZE - 2  # -2 for chunk index
    _chunk_count = (_size + max_chunk - 1) // max_chunk

    if 7 + l_name > MAX_PAYLOAD_SIZE:
        l_name = max_chunk - 7
        file_name = file_name[-l_name:]  # keep end

    buf = bytearray(7 + l_name)

    # pack size in first 4 bytes
    buf[0] = (_size >> 24) & 0xFF
    buf[1] = (_size >> 16) & 0xFF
    buf[2] = (_size >> 8) & 0xFF
    buf[3] = _size & 0xFF

    # pack size in 2 bytes -> meaning file size that can be send is limited
    if _chunk_count > 0xFFFF:
        raise ValueError("File too large")

    buf[4] = (_chunk_count >> 8) & 0xFF
    buf[5] = _chunk_count & 0xFF

    # pack length and name
    buf[6] = l_name
    buf[7 : 7 + l_name] = file_name

    # precompute flags
    f_mid = flags | MESH_FLAG_PARTIAL | MESH_FLAG_FILE
    f_start = f_mid | MESH_FLAG_PARTIAL_START
    f_end = f_mid | MESH_FLAG_PARTIAL_END

    yield build_packet(ptype, src, dst, seq, ttl, f_start, buf, gateway), 0
    del buf

    # reusable buffer
    buf = bytearray(2 + max_chunk)

    with open(file_path, "rb") as f:
        for i in range(_chunk_count):
            chunk = f.read(max_chunk)
            clen = len(chunk)

            if clen == 0:
                break  # safety

            buf[0] = (i >> 8) & 0xFF
            buf[1] = i & 0xFF
            buf[2 : 2 + clen] = chunk

            flags = f_end if i == _chunk_count - 1 else f_mid

            yield (
                build_packet(
                    ptype, src, dst, seq, ttl, flags, buf[: 2 + clen], gateway
                ),
                i,
            )


def encode_neighbour_tuple(_neighbors: dict) -> bytes:
    safe = []
    for entry in _neighbors.values():
        node_id = entry[0]
        mac = entry[1]
        rest = entry[2:]
        safe.append((node_id, mac.hex()) + tuple(rest))
    return ujson.dumps(safe).encode()


def decode_neighbour_bytes(encoded: bytes) -> list:
    raw = ujson.loads(encoded.decode())
    fixed = []
    for entry in raw:
        node_id = entry[0]
        mac_hex = entry[1]
        rest = entry[2:]
        fixed.append((node_id, bytes.fromhex(mac_hex)) + tuple(rest))
    return fixed

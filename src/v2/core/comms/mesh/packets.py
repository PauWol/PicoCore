"""
PicoCore V2 Comms Mesh Packets Utility

This module provides utility functions for the PicoCore V2 Comms Mesh module.
"""

import ustruct as struct
from ..constants import BASE_HEADER_FORMAT_NO_CRC, BASE_HEADER_SIZE_NO_CRC, MESH_VERSION, MAX_PAYLOAD_SIZE, \
    MESH_FLAG_PARTIAL_START, MESH_FLAG_PARTIAL_END, MESH_FLAG_PARTIAL
from ..crc8 import append_crc8_to_bytearray, verify_crc8


def payload_conv(payload: str | bytes | bytearray, _iter: bool = False):
    """
    Convert payload to bytes.
    :param payload:
    :param _iter: If True, return a generator for large payloads (>MAX_PAYLOAD_SIZE=239)
    :return: bytes or generator
    """
    _p = b""
    if isinstance(payload, str):
        _p = payload.encode()
    if isinstance(payload, bytearray):
        _p = payload
    else:
        _p = payload

    if len(_p) > MAX_PAYLOAD_SIZE and not _iter:
        raise ValueError("Payload too large")

    if _iter:
        for i in range(0, len(_p), MAX_PAYLOAD_SIZE):
            yield _p[i:i + MAX_PAYLOAD_SIZE]

    return _p


def build_packet(ptype: int, src: int, dst: int, seq: int,
                 # pylint: disable=too-many-arguments,too-many-positional-arguments
                 ttl: int, flags: int, payload: bytes) -> bytearray:
    """
    Build a mesh packet.
    :param ptype: Payload Type
    :param src: Source Node (0-65535)
    :param dst: Destination Node (0-65535)
    :param seq: Sequence number (0-65535)
    :param ttl: Time To Live (hops)
    :param flags: Flags byte
    :param payload: Payload as bytes (0-255 bytes)
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

    # Pack header without CRC
    header = bytearray(struct.pack(BASE_HEADER_FORMAT_NO_CRC,
                                   version, ptype, src, dst, seq,
                                   ttl, flags, _plen))
    # Append CRC8 of header
    append_crc8_to_bytearray(header)
    # Return final packet
    return header + payload


def _checks(version: int, plen: int, plen_check: int) -> bool:
    """
    Check if the packet is valid.
    :param version:
    :param plen:
    :param plen_check:
    :return:
    """
    return version == MESH_VERSION and plen == plen_check


def parse_packet(packet: bytes) -> tuple[int, int, int, int, int, int, int, int, bytes] | None:
    """
    Parse a mesh packet.
    :param packet: Packet as bytes [header+CRC8+payload]
    :return: Tuple of (version, ptype, src, dst, seq, ttl, flags, plen, payload) or None if invalid
    """
    _header_crc8 = packet[:BASE_HEADER_SIZE_NO_CRC + 1]

    # Header Sum Check
    if not verify_crc8(_header_crc8):
        return None

    _header = _header_crc8[:-1]
    _payload = packet[BASE_HEADER_SIZE_NO_CRC + 1:]

    _version, _ptype, _src, _dst, _seq, _ttl, _flags, _plen \
        = struct.unpack(BASE_HEADER_FORMAT_NO_CRC, _header)

    # Other checks
    if not _checks(_version, _plen, len(_payload)):
        return None

    return _version, _ptype, _src, _dst, _seq, _ttl, _flags, _plen, _payload


def chunk_packet(ptype: int, src: int, dst: int, seq: int,
                 # pylint: disable=too-many-arguments,too-many-positional-arguments
                 ttl: int, flags: int, _payload: str | bytes | bytearray):
    """
    Split up a payload if it exceeds MAX_PAYLOAD_SIZE in multiple messages.

    :param ptype:
    :param src:
    :param dst:
    :param seq:
    :param ttl:
    :param flags:
    :param _payload:
    :yields: the build packets
    """

    if _payload < MAX_PAYLOAD_SIZE:
        yield build_packet(ptype, src, dst, seq, ttl, flags, payload_conv(_payload))

    _chunk_count = len(_payload) / MAX_PAYLOAD_SIZE

    for i, v in enumerate(payload_conv(_payload, True)):

        if i == 0:
            yield build_packet(ptype, src, dst, seq, ttl, flags | MESH_FLAG_PARTIAL_START, v)

        if i == _chunk_count:
            yield build_packet(ptype, src, dst, seq, ttl, flags | MESH_FLAG_PARTIAL_END, v)

        else:

            yield build_packet(ptype, src, dst, seq, ttl, flags | MESH_FLAG_PARTIAL, v)


def encode_neighbour_tuple(data: tuple[int, bytes, int, int, int, int, bool]) -> bytes:
    """
    Encode tuple (int, bytes, int, int, int, int, bool) to bytes.
    Format:
    - int (4 bytes)
    - length of bytes field (4 bytes)
    - bytes field (variable length)
    - int (4 bytes)
    - int (4 bytes)
    - int (4 bytes)
    - int (4 bytes)
    - bool (1 byte)

    :param data: The neighbor as tuple(node_id, mac, version, seq, now, rssi, gateway)
    :return: bytes
    """
    a, b_bytes, c, d, e, f, g = data
    b_len = len(b_bytes)

    # Pack fixed parts + length of bytes field
    header = struct.pack('ii', a, b_len)
    # Pack remaining ints and bool
    tail = struct.pack('iiii?', c, d, e, f, g)

    return header + b_bytes + tail


def decode_neighbour_bytes(encoded: bytes) -> tuple[int, bytes, int, int, int, int, bool]:
    """
    Decode bytes neighbour object back to tuple.

    :param encoded: The neighbor as encoded bytes tuple(node_id, mac, version, seq, now, rssi, gateway)
    :return: tuple(node_id, mac, version, seq, now, rssi, gateway)
    """
    # Unpack first two ints: a and length of bytes field
    a, b_len = struct.unpack('ii', encoded[:8])

    # Extract bytes field
    b_start = 8
    b_end = b_start + b_len
    b_bytes = encoded[b_start:b_end]

    # Unpack remaining ints and bool
    c, d, e, f, g = struct.unpack('iiii?', encoded[b_end:b_end + 17])

    return a, b_bytes, c, d, e, f, g

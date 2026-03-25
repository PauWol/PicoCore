"""
PicoCore V2 Comms Mesh Packets Utility

This module provides utility functions for the PicoCore V2 Comms Mesh module.
"""

import ustruct as struct
import ujson
from core.comms.constants import BASE_HEADER_FORMAT_NO_CRC, BASE_HEADER_SIZE_NO_CRC, MESH_VERSION, MAX_PAYLOAD_SIZE, \
    MESH_FLAG_PARTIAL_START, MESH_FLAG_PARTIAL_END, MESH_FLAG_PARTIAL, MESH_FLAG_GATEWAY
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
        yield _p[i:i + MAX_PAYLOAD_SIZE]

def build_packet(ptype: int, src: int, dst: int, seq: int,
                 # pylint: disable=too-many-arguments,too-many-positional-arguments
                 ttl: int, flags: int, payload: bytes,gateway:bool = False) -> bytearray:
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
        # Pack header without CRC
        header = bytearray(struct.pack(BASE_HEADER_FORMAT_NO_CRC,
                                       version, ptype, src, dst, seq,
                                       ttl, flags | MESH_FLAG_GATEWAY, _plen))
    else:
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
    print("chunking...")
    _plen = len(_payload)

    if _plen <= MAX_PAYLOAD_SIZE:
        print("One Packet")
        yield build_packet(ptype, src, dst, seq, ttl, flags, payload_conv(_payload))
        return

    _chunk_count = (_plen + MAX_PAYLOAD_SIZE - 1) // MAX_PAYLOAD_SIZE
    print(f"chunk count: {_chunk_count}")

    for i, v in enumerate(payload_conv_iter(_payload)):

        if i == 0:
            print("start packet")
            yield build_packet(ptype, src, dst, seq, ttl, flags | MESH_FLAG_PARTIAL_START, v)

        elif i == _chunk_count - 1:
            print("end packet")
            yield build_packet(ptype, src, dst, seq, ttl, flags | MESH_FLAG_PARTIAL_END, v)

        else:
            print("partial packet")
            yield build_packet(ptype, src, dst, seq, ttl, flags | MESH_FLAG_PARTIAL, v)


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

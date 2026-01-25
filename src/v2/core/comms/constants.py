"""
PicoCore V2 Comms Constants

This module provides constants for the PicoCore V2 Comms module.
"""

from micropython import const
import ustruct as struct
#Mesh

# Header: version, type, src, dst, seq, ttl, flags, plen
BASE_HEADER_FORMAT_NO_CRC = "<BBHHHBBB"  # 9 bytes
BASE_HEADER_SIZE_NO_CRC = struct.calcsize(BASE_HEADER_FORMAT_NO_CRC)
CRC8_SIZE = const(2)
MESH_VERSION = const(1)
MAX_NEIGHBORS = const(32)
ESPNOW_MAX_PAYLOAD_SIZE = const(250)
# -------------------------------------------------------------------
# Packet Types
# -------------------------------------------------------------------
MESH_TYPE_HELLO = const(1)   # Node announces itself / joins network
MESH_TYPE_HELLO_ACK = const(2)   # Node acknowledges announcement / transmits routing table
MESH_TYPE_DATA  = const(3)   # Regular data or control payload
MESH_TYPE_ACK   = const(4)   # Acknowledgment for reliable delivery
MESH_TYPE_CTRL  = const(5)   # Reserved for future control messages

# -------------------------------------------------------------------
# Packet Flags (bitwise, can combine with |)
# -------------------------------------------------------------------
MESH_FLAG_NONE       = const(0)        # No flags
MESH_FLAG_ACK        = const(1 << 0)   # Packet expects acknowledgment
MESH_FLAG_BCAST      = const(1 << 1)   # Broadcast to all neighbors
MESH_FLAG_UNICAST    = const(1 << 2)   # Unicast to a specific node
MESH_FLAG_MULTICAST  = const(1 << 3)   # Multicast to a node group
MESH_FLAG_RELIABLE   = const(1 << 4)   # Ensure delivery with retries
MESH_FLAG_UNRELIABLE = const(1 << 5)   # Best-effort delivery
MESH_FLAG_SECURE     = const(1 << 6)   # Encrypted/authenticated
MESH_FLAG_UNSECURE   = const(1 << 7)   # Plain/unencrypted

# -------------------------------------------------------------------
# Default Mesh Parameters
# -------------------------------------------------------------------
DEFAULT_TTL        = const(10)   # Default Time To Live (hops)
MAX_PAYLOAD_SIZE   = ESPNOW_MAX_PAYLOAD_SIZE - (BASE_HEADER_SIZE_NO_CRC + CRC8_SIZE)  # Max payload bytes (fits header)
BROADCAST_ADDR     = const(0xFFFF)
UNDEFINED_NODE_ID  = const(0x0000)  # For uninitialized nodes

BROADCAST_ADDR_MAC = b'\xff\xff\xff\xff\xff\xff'

# -------------------------------------------------------------------
# Mesh Background Task
# -------------------------------------------------------------------
MESH_BACKGROUND_LISTENER_INTERVAL = const(1)
MESH_BACKGROUND_PRIORITY = const(3)
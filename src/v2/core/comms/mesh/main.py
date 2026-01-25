"""
PicoCore V2 Comms Mesh Main

This module provides the PicoCore V2 Comms Mesh main class.
"""
import time
import uselect as select
from network import WLAN, STA_IF
from aioespnow import AIOESPNow
import uasyncio as asyncio
from ..constants import (MAX_NEIGHBORS, MESH_TYPE_HELLO, MESH_TYPE_HELLO_ACK,
                        BROADCAST_ADDR, DEFAULT_TTL, MESH_FLAG_UNSECURE, \
                        MESH_FLAG_BCAST, MESH_FLAG_ACK, UNDEFINED_NODE_ID,
                         BROADCAST_ADDR_MAC, MESH_FLAG_UNICAST, MESH_BACKGROUND_LISTENER_INTERVAL,
                        MESH_BACKGROUND_PRIORITY, MESH_TYPE_DATA
                         )
from ..mesh import RingBuffer, logger
from .packets import build_packet, parse_packet, payload_conv

class Mesh: # pylint: disable=too-many-instance-attributes
    """
    PicoCore V2 Comms Mesh Main Class
    """

    def __init__(self):
        """
        Initialize the Mesh instance.
        """
        self._sequence: int = 0
        self._ttl: int = DEFAULT_TTL
        self._node_id: int = UNDEFINED_NODE_ID
        self._on_recv = None

        self._started: bool = False
        self._wlan: WLAN | None = None
        self._esp: AIOESPNow | None = None
        self._neighbors = RingBuffer(MAX_NEIGHBORS, True)
        self._peers = RingBuffer(MAX_NEIGHBORS, True)
        self._neighbor_index = {} # {node_id: index}
        self._receiving = False
        self._rx_enabled = False
        self._rx_expected_until = 0  # ticks_ms timestamp

    def _up_sequence(self) -> None:
        """
        Increment the sequence number and wrap around at 65535.
        """
        self._sequence += 1
        if self._sequence > 0xFFFF:  # hex for 65535
            self._sequence = 0

    def _is_neighbor(self,node_id:int) -> bool:
        """
        Check if a node is a neighbor.
        :param node_id: The node id as int
        :return:
        """
        return node_id in self._neighbors

    def _get_neighbour(self,node_id: int) -> tuple[int, bytes, int, int, int, int]|object|None:
        """
        Get a neighbor by node id.
        :param node_id: The node id as int
        :return: The neighbor as tuple(node_id, mac, version, seq, now, rssi) or None if not found
        """
        if not self._is_neighbor(node_id):
            return None
        _i = self._neighbor_index[node_id]
        return self._neighbors.peek(_i)

    def _add_neighbor(self, entry: tuple[int, bytes, int, int, int, int]) -> None:
        """
        Add a node to the neighbors list.
        :param entry: (node_id, mac, version, seq, now, rssi)
        :return:
        """
        self._neighbors.put(entry)
        self._neighbor_index[entry[0]] = len(self._neighbors)

    def _remove_neighbor(self,node_id: int) -> None:
        """
        Remove a node from the neighbors list.
        :param node_id: The node id as int
        :return:
        """
        _idx = self._neighbor_index[node_id]
        self._neighbors.clear_index(_idx)
        del self._neighbor_index[node_id]

    def _update_neighbor(self, node_id: int, entry: tuple[int, bytes, int, int, int, int]) -> None:
        """
        Update a node in the neighbors list.
        :param node_id: The node id as int
        :param entry: (node_id, mac, version, seq, now, rssi)
        :return:
        """
        _idx = self._neighbor_index[node_id]
        self._neighbors.put_index(_idx, entry)

    @staticmethod
    def _convert_receive_timeout(timeout: str | float | None) -> int:
        """
        Convert a timeout to milliseconds.
        Input can be a float, a string of the format "1ms" or "1s" or "1min" or "1h" or None.
        :param timeout:
        :return: Timeout in milliseconds or -1 if timeout is None
        """

        if timeout is None:
            return -1

        if isinstance(timeout, str):

            timeout = timeout.lower().strip()

            if timeout.endswith("ms"):
                return int(timeout[:-2])
            if timeout.endswith("s"):
                return int(timeout[:-1]) * 1000
            if timeout.endswith("min"):
                return int(timeout[:-3]) * 1000 * 60
            if timeout.endswith("h"):
                return int(timeout[:-1]) * 1000 * 60 * 60

            raise ValueError("Invalid timeout format")

        return int(timeout * 1000)

    def _send(self, packet, addr, ack: bool = True) -> None:
        """
        Send a packet.
        :param packet:
        :param addr:
        :param ack:
        :return:
        """
        if not self._started:
            raise RuntimeError("Mesh needs to be started before "
                               "sending packets! Use start() to start."
                               )

        self._add(addr)

        self._esp.send(addr, packet, ack)

    async def _async_send(self, packet, addr, ack: bool = True) -> None:
        """
        Send a packet.
        :param packet:
        :param addr:
        :param ack:
        :return:
        """
        if not self._started:
            raise RuntimeError("Mesh needs to be started before "
                               "sending packets! Use start() to start."
                               )

        self._add(addr)

        await self._esp.asend(addr, packet, ack)

    async def _irq(self, host: bytes|bytearray, msg: bytes|bytearray) -> None:
        """
        Interrupt handler for ESPNow on receive.
        :param host:
        :param msg:
        :return:
        """

        _version, _ptype, _src, _dst, _seq, _ttl, _flags, _plen, _payload = parse_packet(msg)

        # Return if packet is from self
        print("SRC",_src)
        print("NODE",self.node_id())
        if _src == self.node_id():
            return

        self.device_registry(host,_src,_version,_seq)

        # packet type check

        if _ptype == MESH_TYPE_HELLO:
            print("HELLO")

            if _flags & MESH_FLAG_ACK:
                print("ACK")
                await self.async_hello_ack(host)

        if _ptype == MESH_TYPE_DATA:
            try:
                # (mac,node_id),(_payload)
                await self._on_recv((host,_src),_payload)

            except Exception as e:
                logger().error(f"Mesh receive error in callback: {e}")

    def _add(self, mac: bytes|bytearray|str) -> None:
        """
        Add a peer to the ESPNow network if it is not already added.
        :param mac:
        :return:
        """
        if not mac in self._peers:
            self._peers.put(mac)
            self._esp.add_peer(mac)

    def is_mac(self, value) -> bool:
        """
        Check whether value is a valid MAC address (bytes or bytearray).

        :param value: Object to validate
        :return: True if valid MAC, False otherwise
        """
        return (
                isinstance(value, (bytes, bytearray)) and
                len(value) == 6
        )

    def _peer(self, peer) -> tuple[int, bytes]:
        """
        Get a peer by node id or MAC address.
        :param peer:
        :return:
        """
        if self._is_node_id(peer):
            entry = self._get_neighbour(peer)
            if entry is None:
                raise ValueError(f"Unknown node ID: {peer}")

            node_id, mac, _, _, _, _ = entry
            return node_id, mac

        if self.is_mac(peer):
            return self.node_id(peer), bytes(peer)

        raise ValueError(
            f"Invalid peer: {peer} | type: {type(peer)} "
            "should be valid MAC address or node ID"
        )

    def _hello(self) -> tuple[bytearray, str]:
        """
        Build a hello packet.
        :return:  (packet,addr)
        """

        # Increment sequence number
        self._up_sequence()

        # Build hello packet
        return build_packet(MESH_TYPE_HELLO, self.node_id(), BROADCAST_ADDR,
                            self._sequence, 1,MESH_FLAG_BCAST | MESH_FLAG_ACK
                            | MESH_FLAG_UNSECURE, b""), BROADCAST_ADDR_MAC

    def _hello_ack(self, host: bytes | bytearray) -> bytearray:
        """
        Send a hello ack packet.
        :param host:
        :return:
        """

        # Increment sequence number
        self._up_sequence()

        # Build hello ack packet
        return build_packet(MESH_TYPE_HELLO_ACK, self.node_id(),
                            self.node_id(host), self._sequence,
                            1, MESH_FLAG_UNICAST | MESH_FLAG_UNSECURE,
                            b""
                            )

    @staticmethod
    def _is_node_id(ref:int|bytes|bytearray) -> bool|None:
        """
          Identify whether ref is a MAC address or a node ID.

          :param ref: bytes/bytearray (MAC) or int (node ID)
          :return: True if ref is a node ID, False if ref is a MAC address, or None if invalid
          """
        # MAC address
        if isinstance(ref, (bytes, bytearray)):
            if len(ref) == 6:
                return False
            return None

        # Node ID
        if isinstance(ref, int):
            # 16-bit node ID derived from MAC[4:6]
            if 0 <= ref <= 0xFFFF:
                return True
            return None

        return None


    def node_id(self, mac: bytes | bytearray= None) -> int:
        """
        Get the Node id of this instance or from input mac if provided.
        :param mac: The host as bytes or bytearray
        :return:  The node id as int
        """
        if mac is not None:
            return (mac[4] << 8) | mac[5]

        if self._node_id is UNDEFINED_NODE_ID:
            mac = self._wlan.config('mac')
            self._node_id = (mac[4] << 8) | mac[5]

        return self._node_id

    def get_rssi(self,mac: bytes|bytearray) -> tuple[int,int]:
        """
        Get the RSSI with timestamp of the last received package from the peer table.
        :return: RSSI as int and timestamp as int
        """
        return self._esp.peers_table.get(mac, [0, 0])

    def device_registry(self, host: bytes|bytearray, src: int, version: int,seq: int) -> None:
        """
        Register/Update a device in the neighbor table.
        :param host: The mac-address from sender
        :param src:
        :param version:
        :param seq:
        :return:
        """
        rssi , ts = self.get_rssi(host)

        if not self._is_neighbor(src):
            self._add_neighbor((src, host, version, seq, ts, rssi))

        else:
            self._update_neighbor(src, (src, host, version, seq, ts, rssi))

    def hello(self) -> None:
        """
        Send a hello packet.
        :return:
        """
        packet, addr = self._hello()
        self._send(packet, addr, False)

    async def async_hello(self) -> None:
        """
        Send a hello packet.
        :return:
        """
        packet, addr = self._hello()
        await self._async_send(packet, addr, False)

    def hello_ack(self, mac: bytes|bytearray) -> None:
        """
        Send a hello ack packet.
        :param mac:
        :return:
        """
        packet = self._hello_ack(mac)
        self._send(packet, mac, False)

    async def async_hello_ack(self, mac: bytes|bytearray) -> None:
        """
        Send a hello ack packet.
        :param mac:
        :return:
        """
        packet = self._hello_ack(mac)
        await self._async_send(packet, mac, False)

    def wait_for_hello_ack(self, node_id: int, timeout: float = 5.0) -> bool:
        """
        Wait until HELLO_ACK is received from a node, i.e., the neighbor is registered.

        :param node_id: The node ID to wait for
        :param timeout: Maximum seconds to wait
        :return: True if neighbor registered, False if timed out
        """
        start = time.ticks_ms()
        while not self._is_neighbor(node_id):
            if time.ticks_diff(time.ticks_ms(), start) > timeout * 1000:
                return False
            time.sleep(0.05)  # small delay to yield CPU
        return True

    async def async_wait_for_hello_ack(self,node_id: int, timeout: float = 5.0) -> bool:
        """
              Wait until HELLO_ACK is received from a node, i.e., the neighbor is registered.

              :param node_id: The node ID to wait for
              :param timeout: Maximum seconds to wait
              :return: True if neighbor registered, False if timed out
              """
        start = time.ticks_ms()
        while not self._is_neighbor(node_id):
            if time.ticks_diff(time.ticks_ms(), start) > timeout * 1000:
                return False
            await asyncio.sleep(0.05)  # small delay to yield CPU
        return True

    def send_data(self,peer: int|bytes|bytearray,payload: str|bytearray|bytes) -> None:
        """
        Send a data packet/packets.
        :param peer:
        :param payload:
        :return:
        """
        _dst_node_id , _mac = self._peer(peer)

        for _p in payload_conv(payload,True):
            self._up_sequence()
            _pb = build_packet(MESH_TYPE_DATA, self.node_id(), _dst_node_id , self._sequence, 1, MESH_FLAG_UNICAST | MESH_FLAG_UNSECURE, _p)

            self._send(_pb, _mac , True)


    async def async_send_data(self,peer: int|bytes|bytearray,payload: str|bytearray|bytes) -> None:
        """
        Send a data packet/packets.
        :param peer:
        :param payload:
        :return:
        """
        _dst_node_id , _mac = self._peer(peer)

        for _p in payload_conv(payload,True):
            self._up_sequence()
            _pb = build_packet(MESH_TYPE_DATA, self.node_id(), _dst_node_id , self._sequence, 1, MESH_FLAG_UNICAST | MESH_FLAG_UNSECURE, _p)

            await self._async_send(_pb, _mac , True)

    def start(self) -> None:
        """
        Start the mesh.
        This will initialize the ESPNow and add the broadcast peer.
        :return:
        """
        if self._started:
            return

        self._wlan = WLAN(STA_IF)
        self._wlan.active(True)
        self._wlan.disconnect()

        self._esp = AIOESPNow()
        self._esp.active(True)

        # Add broadcast peer
        self._add(BROADCAST_ADDR_MAC)

        self._started = True
        self.node_id() #<-- force node id to be set


    def stop(self):
        """
        Stop the mesh.
        This will turn off espnow and wlan.
        :return:
        """
        if not self._started:
            return

        self.rx_disable()
        self._esp.active(False)
        self._wlan.active(False)

        #reset states
        self._receiving = False
        self._started = False

    def rx_enable(self, listen_ms: int | None = None):
        """
        Enable receiving packets.
        :param listen_ms:
        :return:
        """
        if not self._started:
            self.start()
        self._rx_enabled = True
        if listen_ms is not None:
            from time import ticks_ms, ticks_add
            self._rx_expected_until = ticks_add(ticks_ms(), listen_ms)
        else:
            self._rx_expected_until = 0  # indefinite

    def rx_disable(self):
        """
        Disable receiving packets.
        :return:
        """
        self._rx_enabled = False
        self._rx_expected_until = 0

    def rx_expected(self) -> bool:
        """
        Check if receiving is expected.
        :return:
        """
        if not self._rx_enabled:
            return False
        if self._rx_expected_until == 0:
            return True
        from time import ticks_ms, ticks_diff
        return ticks_diff(self._rx_expected_until, ticks_ms()) > 0

    def callback(self, callback) -> None:
        """
        Register a callback function to be called when a packet is received.
        Note: The callback function should have the signature: callback(host, msg)
        or callback(*args).

        - host: tuple -> (mac,node_id)
        - msg: bytes|bytearray -> payload

        :param callback:
        :return:
        """
        self._on_recv = callback

    async def receive_task(self):
        """
        This is the receive task.
        :return:
        """
        self.start()
        while True:
            if not self._rx_enabled:
                # nothing expected → idle cheaply
                await asyncio.sleep_ms(250)
                continue

            try:
                host, msg = await self._esp.airecv()
                if host and msg:
                    await self._irq(host, msg)
            except Exception as e:
                logger().error(f"mesh rx error: {e}")
                await asyncio.sleep_ms(20)

    def stats(self):
        """
        Return mesh statistics.
        :return: (tx_pkts, tx_responses, tx_failures, rx_packets, rx_dropped_packets, started, receiving, node_id, mac, sequence, registered_neighbors_count)
        """
        return self._esp.stats(), self._started, self._receiving, self._node_id, self._wlan.config('mac'), self._sequence, self._neighbors.available()


_mesh: Mesh|None = None

def mesh() -> Mesh:
    """
    This returns the Mesh instance.
    :return:
    """
    global _mesh
    if _mesh is None:
        _mesh = Mesh()
    return _mesh


def mesh_callback():
    """
    Decorator to set the mesh callback function.
    Register a callback function to be called when a packet is received.

    Note: The callback function should have the signature: callback(host, msg) or callback(*args).

    - More info on https://pauwol.github.io/PicoCore/api/overview/ #TODO: Change to right URL.
    - host: tuple -> (mac,node_id)
    - msg: bytes|bytearray -> payload

    :return:
    """
    def deco(fn):
        mesh().callback(fn)
        return fn
    return deco
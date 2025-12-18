"""
PicoCore V2 Comms Mesh Main

This module provides the PicoCore V2 Comms Mesh main class.
"""

from network import WLAN, STA_IF
from espnow import ESPNow
from ..constants import MAX_NEIGHBORS, MESH_TYPE_HELLO, MESH_TYPE_HELLO_ACK, BROADCAST_ADDR, DEFAULT_TTL, MESH_FLAG_UNSECURE, \
    MESH_FLAG_BCAST, MESH_FLAG_ACK, UNDEFINED_NODE_ID, BROADCAST_ADDR_MAC, MESH_FLAG_UNICAST
from ..mesh import RingBuffer, logger
from .packets import build_packet, parse_packet
import time
import select

class Mesh:
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
        self._esp: ESPNow | None = None
        self._neighbors = RingBuffer(MAX_NEIGHBORS, True)
        self._peers = RingBuffer(MAX_NEIGHBORS, True)
        self._neighbor_index = {}

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

    def _add_neighbor(self, entry: tuple[int, bytes, int, int, int]) -> None:
        """
        Add a node to the neighbors list.
        :param entry: (node_id, host, version, now, rssi)
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

    def _update_neighbor(self, node_id: int, entry: tuple[int, bytes, int, int, int]) -> None:
        """
        Update a node in the neighbors list.
        :param node_id: The node id as int
        :param entry: (node_id, host, version, now, rssi)
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
            elif timeout.endswith("s"):
                return int(timeout[:-1]) * 1000
            elif timeout.endswith("min"):
                return int(timeout[:-3]) * 1000 * 60
            elif timeout.endswith("h"):
                return int(timeout[:-1]) * 1000 * 60 * 60
            else:
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
            raise RuntimeError("Mesh needs to be started before sending packets! Use start() to start.")

        self._add(addr)

        self._esp.send(addr, packet, ack)

    def _irq(self, host: bytes|bytearray, msg: bytes|bytearray) -> None:
        """
        Interrupt handler for ESPNow on receive.
        :param host:
        :param msg:
        :return:
        """

        _version, _ptype, _src, _dst, _seq, _ttl, _flags, _plen, _payload = parse_packet(msg)

        # Return if packet is from self
        if _src == self.node_id():
            return

        self.device_registry(host,_src,_version)

        # packet type check

        if _ptype == MESH_TYPE_HELLO:

            if _flags & MESH_FLAG_ACK:
                self.hello_ack(host)

    def _add(self, mac: bytes|bytearray|str) -> None:
        """
        Add a peer to the ESPNow network if it is not already added.
        :param mac:
        :return:
        """
        if not mac in self._peers:
            self._peers.put(mac)
            self._esp.add_peer(mac)

    def _hello(self) -> tuple[bytearray, str]:
        """
        Build a hello packet.
        :return:  (packet,addr)
        """

        # Increment sequence number
        self._up_sequence()

        # Build hello packet
        return build_packet(MESH_TYPE_HELLO, self.node_id(), BROADCAST_ADDR, self._sequence, 1,
                            MESH_FLAG_BCAST | MESH_FLAG_ACK | MESH_FLAG_UNSECURE, b""), BROADCAST_ADDR_MAC

    def _hello_ack(self, host: bytes | bytearray) -> bytearray:
        """
        Send a hello ack packet.
        :param host:
        :return:
        """

        # Increment sequence number
        self._up_sequence()

        # Build hello ack packet
        return build_packet(MESH_TYPE_HELLO_ACK, self.node_id(), self.node_id(host), self._sequence, 1, MESH_FLAG_UNICAST | MESH_FLAG_UNSECURE, b"")

    def node_id(self, host: bytes | bytearray= None) -> int:
        """
        Get the Node id of this instance or from input host if provided.
        :param host: The host as bytes or bytearray
        :return:  The node id as int
        """
        if host is not None:
            return (host[4] << 8) | host[5]

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

    def device_registry(self, host: bytes|bytearray, src: int, version: int):
        """
        Register/Update a device in the neighbor table.
        :param host:
        :param src:
        :param version:
        :return:
        """
        rssi , ts = self.get_rssi(host)

        if not self._is_neighbor(src):
            self._add_neighbor((src, host, version, ts, rssi))

        else:
            self._update_neighbor(src, (src, host, version, ts, rssi))

    def hello(self) -> None:
        """
        Send a hello packet.
        :return:
        """
        packet, addr = self._hello()
        self._send(packet, addr, False)

    def hello_ack(self, mac) -> None:
        """
        Send a hello ack packet.
        :param mac:
        :return:
        """
        packet = self._hello_ack(mac)
        self._send(packet, mac, False)


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

        self._esp = ESPNow()
        self._esp.active(True)

        # Add broadcast peer
        self._add(BROADCAST_ADDR_MAC)

        self._started = True

    def stop(self):
        """
        Stop the mesh.
        This will turn off espnow and wlan.
        :return:
        """
        if not self._started:
            return

        self._esp.active(False)
        self._wlan.active(False)

        self._started = False

    def callback(self, callback) -> None:
        """
        Register a callback function to be called when a packet is received.
        Note: The callback function should have the signature: callback(host, msg) or callback(*args)
        :param callback:
        :return:
        """
        self._on_recv = callback

    def receive(self, timeout: float | None = 0, result: bool = False) -> list[tuple[
        bytes | bytearray | None, bytes | bytearray | None]] | None:
        """
        Receive packets for given timeout (float seconds) or infinite if timeout is None.
        If result is True return a list of (host, msg) tuples.
        """
        self.start()

        _poll_timeout = self._convert_receive_timeout(timeout)  # milliseconds or -1 for infinite
        _start = time.ticks_ms()

        _result = [] if result else None

        # create poller once
        poller = select.poll()
        poller.register(self._esp, select.POLLIN)

        # Helper to compute remaining timeout per poll call (ms)
        def remaining_ms():
            if _poll_timeout == -1:
                return -1
            elapsed = time.ticks_diff(time.ticks_ms(), _start)  # elapsed ms
            rem = _poll_timeout - elapsed
            return rem if rem > 0 else 0

        while True:
            rt = remaining_ms()
            # If not infinite and time is up -> break
            if _poll_timeout != -1 and rt == 0:
                break

            events = poller.poll(rt)

            if not events:
                continue

            host, msg = self._esp.irecv()

            if not host and not msg:
                continue

            if result:
                _result.append((host, msg))

            try:
                self._irq(host, msg)
            except Exception as err:
                logger().error(f"Mesh IRQ error: {err}")

            # call registered callback
            if self._on_recv:
                try:
                    self._on_recv(host, msg)
                except Exception as err:
                    logger().error(f"Mesh receive callback error: {err}")

        self.stop()

        return _result if result and _result else None

    def receive_nonblocking(self, result: bool = False) -> list[tuple[
        bytes | bytearray | None, bytes | bytearray | None]] | None:
        """
        Non-blocking receive: process any waiting packets and return immediately.
        """
        self.start()

        _result = [] if result else None

        poller = select.poll()
        poller.register(self._esp, select.POLLIN)

        events = poller.poll(0)
        if not events:
            return _result if result else None

        while events:
            host, msg = self._esp.irecv()
            if host or msg:
                if result:
                    _result.append((host, msg))

                try:
                    self._irq(host, msg)
                except Exception as err:
                    logger().error(f"Mesh IRQ error: {err}")

                if self._on_recv:
                    try:
                        self._on_recv(host, msg)
                    except Exception as err:
                        logger().error(f"Mesh receive callback error: {err}")

            # poll again to process remaining messages
            events = poller.poll(0)

        return _result if result else None

    def state(self):
        pass

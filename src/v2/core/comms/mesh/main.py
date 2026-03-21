"""
PicoCore V2 Comms Mesh Main

This module provides the PicoCore V2 Comms Mesh main class.
"""
import time
from network import WLAN, STA_IF
from aioespnow import AIOESPNow
import uasyncio as asyncio
from ..constants import (MAX_NEIGHBORS, MESH_TYPE_HELLO, MESH_TYPE_HELLO_ACK,
                         BROADCAST_ADDR, DEFAULT_TTL, MESH_FLAG_UNSECURE, \
                         MESH_FLAG_BCAST, MESH_FLAG_ACK, UNDEFINED_NODE_ID,
                         BROADCAST_ADDR_MAC, MESH_FLAG_UNICAST, MESH_TYPE_DATA, \
                         MAX_PMK_BYTE_LEN, PMK_DEFAULT_KEY, MESH_FLAG_GATEWAY, MESH_FLAG_PARTIAL, MESH_FLAG_PARTIAL_END,
                         MESH_FLAG_PARTIAL_START
                         )
from .. import RingBuffer, logger, get_config, MESH_SECRET
from .packets import build_packet, parse_packet, chunk_packet, encode_neighbour_tuple, \
    decode_neighbour_bytes, payload_conv_iter


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
        self._neighbors = {} # TODO: Maybe add fixed leng dict with * MAX_NEIGHBORS
        self._peers = RingBuffer(MAX_NEIGHBORS, True)
        self._neighbor_index = {} # {node_id: index}+
        self._receiving = False
        self._rx_enabled = False
        self._rx_expected_until = 0  # ticks_ms timestamp
        self._raw_recv_callback_data = False
        self._fragments = {}  # (src, seq) -> [chunks]
        self._neighbor_timeout = 30000  # 30s

        self._seen_packets = set()
        self._seen_limit = 100
        self._seen_queue = RingBuffer(self._seen_limit + 1)

    # Helper section ---------------------------------------------------------

    @staticmethod
    def is_mac(value) -> bool:
        """
        Check whether value is a valid MAC address (bytes or bytearray).

        :param value: Object to validate
        :return: True if valid MAC, False otherwise
        """
        return (
                isinstance(value, (bytes, bytearray)) and
                len(value) == 6
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

    # Sequencing section ---------------------------------------------------------------

    def _up_sequence(self) -> None:
        """
        Increment the sequence number and wrap around at 65535.
        """
        self._sequence += 1
        if self._sequence > 0xFFFF:  # hex for 65535
            self._sequence = 0

    def _seen(self, src, seq):
        key = (src, seq)
        if key in self._seen_packets:
            return True

        self._seen_packets.add(key)
        self._seen_queue.put(key)

        if len(self._seen_queue) > self._seen_limit:
            old = self._seen_queue.get()
            self._seen_packets.remove(old)

        return False

    # Neighbor section -----------------------------------------------------------------
    # TODO: Review neighbor and routing logic as it may lead to runtime errors if sending to indirect neighbor node that is out of range
    # Data structures:
    #
    # - neighbor entry -> tuple (node_id, mac, version, seq, ts, rssi, gateway)


    def _add_neighbor(self, entry) -> None:
        """
        Add a neighbor to the known dict.
        """
        logger().debug(f"Adding neighbor: {entry}")
        self._neighbors[entry[0]] = entry

    def _get_neighbour(self, node_id: int):
        """
        Get a neighbor from the known dict.

        :returns: The neighbor entry as tuple ()
        """
        return self._neighbors.get(node_id)

    def _is_neighbor(self, node_id: int) -> bool:
        """
        Check if a node is a neighbor

        :param node_id:
        :returns:
        """
        return node_id in self._neighbors

    def _update_neighbor(self,node_id:int ,entry)-> None:
        """
        Update a neighbor entry.
        """
        self._neighbors[node_id] = entry

    def _cleanup_neighbors(self):
        now = time.ticks_ms()

        for node, entry in list(self._neighbors.items()):
            _, _, _, _, ts, _, _ = entry

            if time.ticks_diff(now, ts) > self._neighbor_timeout:
                del self._neighbors[node]

    def _remove_neighbor(self,node_id: int) -> None:
        """
        Remove a node from the neighbors list.
        :param node_id: The node id as int
        :return:
        """
        if self._is_neighbor(node_id):
            del self._neighbors[node_id]

    def _add(self, mac: bytes|bytearray|str) -> None:
        """
        Add a peer to the ESPNow network if it is not already added.
        :param mac:
        :return:
        """
        if not mac in self._peers:
            self._peers.put(mac)
            self._esp.add_peer(mac)

    def _peer(self, peer) -> tuple[int, bytes]:
        """
        Get a peer by node id or MAC address.
        :param peer:
        :return:
        """
        if self._is_node_id(peer):
            entry = self._get_neighbour(peer)
            if entry is None:
                raise ValueError(
                    f"Unknown node ID: {peer}"
                    "\nConsider using wait_for_hello_ack / async_wait_for_hello_ack "
                    "to ensure target is registered neighbor"
                                 )

            node_id, mac, _, _, _, _, _ = entry
            return node_id, mac

        if self.is_mac(peer):
            return self.node_id(peer), bytes(peer)

        raise ValueError(
            f"Invalid peer: {peer} | type: {type(peer)} "
            "should be valid MAC address or node ID"
        )

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

    def device_registry(self, host: bytes|bytearray, src: int, version: int, seq: int, gateway: bool = False) -> None:
        """
        Register/Update a device in the neighbor table.
        :param host: The mac-address from sender
        :param src:
        :param version:
        :param seq:
        :param gateway:
        :return:
        """
        rssi , ts = self.get_rssi(host)

        if not self._is_neighbor(src):
            self._add_neighbor((src, host, version, seq, ts, rssi,gateway))

        else:
            self._update_neighbor(src, (src, host, version, seq, ts, rssi, gateway))

        self._cleanup_neighbors()


    # Security section ----------------------------------------------------------------

    @staticmethod
    def _is_pmk_valid(pmk: bytes|bytearray|str) -> bool:
        """
        Perform validity checks for the custom user pmk.

        :return:
        """
        return 0 < len(pmk) <= MAX_PMK_BYTE_LEN

    def _update_pmk(self,pmk: bytes|bytearray|str) -> None:
        """
        Set the primary master key for encryption.

        :return:
        """
        _pmk_l = pmk

        if not self._is_pmk_valid(pmk):
            _pmk_l = PMK_DEFAULT_KEY

        self._esp.set_pmk(_pmk_l)

    # Messaging section --------------------------------------------------------------------

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

    async def _async_resend(self,):
        pass


    async def _irq(self, host: bytes|bytearray, msg: bytes|bytearray) -> None:
        """
        Interrupt handler for ESPNow on receive.
        :param host:
        :param msg:
        :return:
        """

        parsed = parse_packet(msg)
        if not parsed:
            return
        _version, _ptype, _src, _dst, _seq, _ttl, _flags, _plen, _payload = parsed


        # Return if packet is from self
        if _src == self.node_id():
           return

        key = (_src, _seq)
        # DROP duplicates if not partial
        if not (_flags & MESH_FLAG_PARTIAL):
            if self._seen(*key):
                return

        if _flags & MESH_FLAG_GATEWAY:
            self.device_registry(host,_src,_version,_seq,True)

        else:
            self.device_registry(host, _src, _version, _seq, False)

        # packet type check

        if _ptype == MESH_TYPE_HELLO:
            logger().debug("HELLO packet received")

            if _flags & MESH_FLAG_ACK:
                await self.async_hello_ack(host)
                logger().debug("HELLO_ACK sent")
                return

        if _ptype == MESH_TYPE_HELLO_ACK and _dst == self.node_id():
            logger().debug("HELLO_ACK packet received")

            neighbors = decode_neighbour_bytes(_payload)
            logger().debug(f"Neighbors: {neighbors}")
            for n in neighbors:
                n = tuple(n)
                if n[0] == self.node_id():
                    continue
                self._add_neighbor(n)
            return



        # FORWARD if not for us
        if _dst != self.node_id() and (_ptype == MESH_TYPE_DATA or _ptype == MESH_TYPE_HELLO_ACK):
            logger().debug("Forwarding")
            if _ttl > 1:
                _ttl -= 1

                fwd_packet = build_packet(
                    _ptype, _src, _dst, _seq,
                    _ttl, _flags, _payload
                )

                # broadcast forward (simple flooding)
                self._esp.send(BROADCAST_ADDR_MAC, fwd_packet, False)

            return


        if _ptype == MESH_TYPE_DATA:
            logger().debug("DATA packet received")

            if _flags & MESH_FLAG_PARTIAL:
                if _flags & MESH_FLAG_PARTIAL_START:
                    self._fragments[key] = []

                if key not in self._fragments:
                    return  # drop invalid sequence

                self._fragments[key].append(_payload)

                if _flags & MESH_FLAG_PARTIAL_END:
                    full = b''.join(self._fragments[key])
                    del self._fragments[key]
                    _payload = full
                else:
                    return

            try:
                # (mac,node_id),(_payload)
                if not self._raw_recv_callback_data:
                    _payload = _payload.decode("utf-8")
                if self._on_recv:
                    await self._on_recv((host, _src), _payload)
            except TypeError as e:
                logger().error( "Hint: Mesh callback must be async and use 'async def'"
                                "Note: ensure the function contains at least one 'await' " 
                                "(e.g. 'await asyncio.sleep(0)') to avoid blocking the scheduler."
                            )
                logger().error(f"Original Mesh receive error: {e}")
            except Exception as e:
                logger().error(f"Mesh receive error in callback: {e}")

    def _hello(self) -> tuple[bytearray, str]:
        """
        Build a hello packet.
        :return:  (packet,addr)
        """

        # Increment sequence number
        self._up_sequence()

        # Build hello packet
        return build_packet(MESH_TYPE_HELLO, self.node_id(), BROADCAST_ADDR,
                            self._sequence, self._ttl,MESH_FLAG_BCAST | MESH_FLAG_ACK
                            | MESH_FLAG_UNSECURE, b""), BROADCAST_ADDR_MAC

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

    def _hello_ack(self,mac: bytes|bytearray) -> tuple[int,int,int,int,int,int,bytes]:
        """
        Build the hello_ack packet.

        :param mac:
        :returns: the packet as tuple
        """
        _payload = encode_neighbour_tuple(self._neighbors)
        logger().debug(f"HELLO_ACK _payload: {_payload}")
        _flags = MESH_FLAG_UNICAST | MESH_FLAG_UNSECURE

        self._up_sequence()

        return MESH_TYPE_HELLO_ACK, self.node_id(),self.node_id(mac), self._sequence, self._ttl, _flags, _payload

    def hello_ack(self, mac: bytes|bytearray) -> None:
        """
        Send a hello ack packet.
        :param mac:
        :return:
        """
        _pkt = self._hello_ack(mac)

        for _p in chunk_packet(*_pkt):
            logger().debug("Sending chunk...")
            self._send(_p, mac, False)

    async def async_hello_ack(self, mac: bytes|bytearray) -> None:
        """
        Send a hello ack packet (share own neighbor table).
        :param mac:
        :return:
        """
        _pkt = self._hello_ack(mac)

        for _p in chunk_packet(*_pkt):
            logger().debug("Sending chunk...")
            await self._async_send(_p, mac, False)

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

        for _p in payload_conv_iter(payload):
            self._up_sequence()
            _pb = build_packet(MESH_TYPE_DATA, self.node_id(), _dst_node_id , self._sequence, self._ttl, MESH_FLAG_UNICAST | MESH_FLAG_UNSECURE, _p)

            self._send(_pb, _mac , True)


    async def async_send_data(self,peer: int|bytes|bytearray,payload: str|bytearray|bytes) -> None:
        """
        Send a data packet/packets.
        :param peer:
        :param payload:
        :return:
        """
        _dst_node_id , _mac = self._peer(peer)

        for _p in payload_conv_iter(payload):
            self._up_sequence()
            _pb = build_packet(MESH_TYPE_DATA, self.node_id(), _dst_node_id , self._sequence, self._ttl, MESH_FLAG_UNICAST | MESH_FLAG_UNSECURE, _p)

            await self._async_send(_pb, _mac , True)

    # Mesh Runtime section -----------------------------------------------------------

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

        _conf = get_config()

        _secret = str(_conf.get(MESH_SECRET))

        if _secret:
            time.sleep_ms(200)
            self._update_pmk(_secret)

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

    def callback(self, callback, raw: bool = False) -> None:
        """
        Register a callback function to be called when a packet is received.
        Note: The callback function should have the signature: callback(host, msg)
        or callback(*args).

        - host: tuple -> (mac,node_id)
        - msg: bytes|bytearray -> payload

        :param callback:
        :param raw: Whether the payload should automatically be decoded (utf-8) or not -> false == decoded
        :return:
        """
        self._raw_recv_callback_data = raw
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



    # Information section --------------------------------------------------------------------------------

    def stats(self):
        """
        Return mesh statistics.
        :return: (tx_pkts, tx_responses, tx_failures, rx_packets, rx_dropped_packets, started, receiving, node_id, mac, sequence, registered_neighbors_count)
        """
        return self._esp.stats(), self._started, self._receiving, self._node_id, self._wlan.config('mac'), self._sequence, len(self._neighbors)




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

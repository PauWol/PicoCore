"""
PicoCore V2 Comms Mesh Main

This module provides the PicoCore V2 Comms Mesh main class.
"""

import time
import gc
from network import WLAN, STA_IF
from aioespnow import AIOESPNow
import uasyncio as asyncio
from core.comms.constants import (
    MAX_NEIGHBORS,
    MESH_TYPE_HELLO,
    MESH_TYPE_HELLO_ACK,
    BROADCAST_ADDR,
    DEFAULT_TTL,
    MESH_FLAG_BCAST,
    MESH_FLAG_ACK,
    UNDEFINED_NODE_ID,
    BROADCAST_ADDR_MAC,
    MESH_FLAG_UNICAST,
    MESH_TYPE_DATA,
    PMK_BYTE_LEN,
    PMK_DEFAULT_KEY,
    MESH_FLAG_GATEWAY,
    MESH_FLAG_PARTIAL,
    MESH_FLAG_PARTIAL_END,
    MESH_FLAG_PARTIAL_START,
    MESH_CLEAN_INTERVAL,
    MESH_HELLO_INTERVAL,
    ESPNOW_WIFI_CHANNEL,
    ESPNOW_WIFI_TXPOWER,
)
from core.constants import MESH_SECRET, MESH_GATEWAY
from core.queue import RingBuffer
from core.logging import logger
from core.config import get_config
from .packets import (
    build_packet,
    parse_packet,
    chunk_packet,
    encode_neighbour_tuple,
    decode_neighbour_bytes,
)


class NodeNotFoundError(Exception):
    pass


class Mesh:  # pylint: disable=too-many-instance-attributes
    """
    PicoCore V2 Comms Mesh Main Class
    """

    def __init__(self):
        """
        Initialize the Mesh instance.
        """
        cfg = get_config()

        self._sequence: int = 0
        self._ttl: int = DEFAULT_TTL
        self._node_id: int = UNDEFINED_NODE_ID
        self._on_recv = None

        self._started: bool = False
        self._starting = False
        self._wlan: WLAN | None = None
        self._esp: AIOESPNow | None = None
        self._neighbors = {}  # TODO: Maybe add fixed leng dict with * MAX_NEIGHBORS
        self._peers = RingBuffer(MAX_NEIGHBORS, True)
        self._neighbor_index = {}  # {node_id: index}+
        self._receiving = False
        self._rx_enabled = False
        self._rx_expected_until = 0  # ticks_ms timestamp
        self._raw_recv_callback_data = False
        self._fragments = {}  # (src, seq) -> [chunks]
        self._neighbor_timeout = 30000  # 30s

        self._seen_packets = set()
        self._seen_limit = 100
        self._seen_queue = RingBuffer(self._seen_limit + 1)

        self._gateway = bool(cfg.get(MESH_GATEWAY)) if not None else False

    # Helper section ---------------------------------------------------------

    @staticmethod
    def is_mac(value) -> bool:
        """
        Check whether value is a valid MAC address (bytes or bytearray).

        :param value: Object to validate
        :return: True if valid MAC, False otherwise
        """
        return isinstance(value, (bytes, bytearray)) and len(value) == 6

    @staticmethod
    def _is_node_id(ref: int | bytes | bytearray) -> bool | None:
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
    #
    # Data structures:
    #
    # - neighbor entry -> node_id : tuple (node_id, mac, version, seq, ts, rssi, gateway)
    # - route entry -> node_id : node_id, score
    # TODO: Remove routes dict solution as it implies to much RAM usage. Rely on previous neighbor table by introducing none atomic data structure.
    #  Meaning the indirect neighbors only store a quality score and which direct neighbor to use to get to it.
    #  The score is used to determine whether to keep or replace a route up on new data.

    @staticmethod
    def score(x, now):
        """
        Create a score for a set of values.
        A higher score is better
        """
        # x = (timestamp, rssi, is_gateway)
        ts = x[0]
        rssi = x[1]
        is_gw = x[2]

        # age penalty (older = worse)
        age = time.ticks_diff(now, ts)

        # weights (tune these!)
        gw_bonus = 20 if is_gw else 0
        rssi_weight = rssi  # already negative scale
        age_penalty = age * 0.1  # small decay

        return rssi_weight + gw_bonus - age_penalty

    @staticmethod
    def process_route_entry(from_node_id: int, from_mac: bytes, entry: tuple):
        """
        Basically extracting target and setting how to get to it.

        :param from_node_id:
        :param from_mac:
        :param entry: The receiver neighbor entry.

        :returns: key (target node_id) , entry (information about target and how to reach it)
        """
        _key = entry[0]
        _ne = (from_node_id, from_mac) + entry[1:]

        return _key, _ne

    @staticmethod
    def _is_direct(key: int, entry):
        return key == entry[0]

    def _add_received_neighbor(self, key: int, entry):
        """
        Add a neighbor's neighbor.

        Note: entry[0] is the node_id of the node sending the data, meaning only the knowledge that the node sending me the data knows the destination is embedded
        """
        if key == self.node_id():
            return

        _entry = self._neighbors.get(key)

        if _entry is None:
            # New neighbor is unknown

            now = time.ticks_ms()
            if self._is_direct(key, entry):
                # If I don't know a direct neighbor sent to me -> it has to be one of the sender that's out of my reach.
                # Meaning I have now gained an indirect route using a direct, thus the direct and score is stored.
                self._neighbors[key] = (entry[0], self.score(entry[4:], now))
                return

            self._neighbors[key] = entry
            return

        # Return if already direct route exists
        if _entry and self._is_direct(key, _entry):
            return

        now = time.ticks_ms()
        _ns = self.score(entry[4:], now)

        # If the new route is better than the old indirect route use the new
        if _entry and _entry[1] < _ns:
            self._neighbors[key] = (_entry[0], _ns)
            return

    def _add_neighbor(self, key: int, entry) -> None:
        """
        Add a neighbor to the known dict.
        """
        if key == self.node_id():
            return
        logger().debug(f"Adding neighbor: {entry}")
        self._neighbors[key] = entry

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

    def _update_neighbor(self, node_id: int, entry) -> None:
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

    def _remove_neighbor(self, node_id: int) -> None:
        """
        Remove a node from the neighbors list.
        :param node_id: The node id as int
        :return:
        """
        if self._is_neighbor(node_id):
            del self._neighbors[node_id]

    def _add(self, mac: bytes | bytearray | str) -> None:
        """
        Add a peer to the ESPNow network if it is not already added.
        :param mac:
        :return:
        """
        if mac not in self._peers:
            self._peers.put(mac)
            self._esp.add_peer(mac)

    def _peer(self, peer: int | bytes) -> tuple[int, bytes]:
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
            if len(entry) == 2:
                logger().debug(f"Getting direct mac for indirect entry: {entry}")
                return self._get_neighbour(entry[0])

            node_id, mac, _, _, _, _, _ = entry
            logger().debug(f"Returning direct neighbor: {node_id}")
            return node_id, mac

        if self.is_mac(peer):
            return self.node_id(peer), bytes(peer)

        raise ValueError(
            f"Invalid peer: {peer} | type: {type(peer)} "
            "should be valid MAC address or node ID"
        )

    def node_id(self, mac: bytes | bytearray = None) -> int:
        """
        Get the Node id of this instance or from input MAC if provided.
        :param mac: The host as bytes or bytearray
        :return:  The node id as int
        """
        if mac is not None:
            return (mac[4] << 8) | mac[5]

        if self._node_id is UNDEFINED_NODE_ID:
            mac = self._wlan.config("mac")
            self._node_id = (mac[4] << 8) | mac[5]

        return self._node_id

    def get_rssi(self, mac: bytes | bytearray) -> tuple[int, int]:
        """
        Get the RSSI with timestamp of the last received package from the peer table.
        :return: RSSI as int and timestamp as int
        """
        return self._esp.peers_table.get(mac, [0, 0])

    def device_registry(
        self,
        host: bytes | bytearray,
        src: int,
        version: int,
        seq: int,
        gateway: bool = False,
    ) -> None:
        """
        Register/Update a device in the neighbor table.
        :param host: The mac-address from sender
        :param src:
        :param version:
        :param seq:
        :param gateway:
        :return:
        """
        rssi, ts = self.get_rssi(host)

        if not self._is_neighbor(src):
            self._add_neighbor(src, (src, host, version, seq, ts, rssi, gateway))

        else:
            self._update_neighbor(src, (src, host, version, seq, ts, rssi, gateway))

        self._cleanup_neighbors()

    # Security section ----------------------------------------------------------------
    # Core idea is symmetric cipher.
    # But as encryption only happens when the devices register each other we plan to implement software level encryption.
    # Meaning all devices with same key can safely broadcast, multicast or singlecast.
    # This trusted device approach is simple and may need revision after its testing phase.
    # TODO: Implement actual working encryption.

    @staticmethod
    def _is_pmk_valid(pmk: bytes | bytearray | str) -> bool:
        """
        Perform validity checks for the custom user pmk.

        :return:
        """
        return len(pmk) == PMK_BYTE_LEN

    def _update_pmk(self, pmk: bytes | bytearray | str) -> None:
        """
        Set the primary master key for encryption.

        :return:
        """
        _pmk_l = pmk

        if not self._is_pmk_valid(pmk):
            logger().warn(
                f"PMK: {pmk} is invlaid length needs to be {PMK_BYTE_LEN}.Using default pmk!"
            )
            _pmk_l = PMK_DEFAULT_KEY

        self._esp.set_pmk(_pmk_l)

    # Routing section ----------------------------------------------------------------------
    #
    # For no routing is:
    # Before development of this logic an already better algorithm is planned.
    #
    # Algorithm Idea:
    # As the send method needs a mac-address or needs to broadcast to all peers, we have to plug in a pre-defining target layer.
    # Hence, we incorporate a decision tree:
    #
    # Desired target in range?
    #
    # YES -> send directly
    #
    # NO:
    # Do I have any neighbors who might now the target?
    #
    # YES -> send to them
    # NO -> Broadcast to all
    #

    def target(self, dst_node_id: int, not_found_error: bool = False) -> bytes:
        """
        Return the mac address to reach a certain target with dst_node_id.

        :param dst_node_id: The node_id of the desired target to send the message to.
        :param not_found_error: When True it throws an error instead of Broadcasting when target is not in neighbor list.
        """
        if not self._is_node_id(dst_node_id):
            raise ValueError(
                f"Destination node_id: {dst_node_id} is not valid node_id."
            )

        if dst_node_id == self.node_id():
            raise ValueError("Cannot send to self")

        if self._is_neighbor(dst_node_id):
            logger().debug(f"{dst_node_id} is neighbor")
            _, mac = self._peer(dst_node_id)
            return mac

        if not_found_error:
            raise NodeNotFoundError(
                f"Node dst_node_id: {dst_node_id} not found."
                "\nConsider using wait_for_hello_ack / async_wait_for_hello_ack"
                "to ensure target is registered neighbor."
                "\nOr set not_found_error to False to broadcast in this case."
            )

        return BROADCAST_ADDR_MAC

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
            raise RuntimeError(
                "Mesh needs to be started before sending packets! Use start() to start."
            )

        self._add(addr)

        self._esp.send(addr, packet, ack)
        time.sleep_ms(5)

    async def _async_send(self, packet, addr, ack: bool = True) -> None:
        """
        Send a packet.
        :param packet:
        :param addr:
        :param ack:
        :return:
        """
        if not self._started:
            raise RuntimeError(
                "Mesh needs to be started before sending packets! Use start() to start."
            )

        self._add(addr)

        await self._esp.asend(addr, packet, ack)
        await asyncio.sleep_ms(5)

    async def _irq(self, host: bytes | bytearray, msg: bytes | bytearray) -> None:
        """
        Interrupt handler for ESPNow on receive.
        :param host:
        :param msg:
        :return:
        """
        # TODO: Update this function for efficiency repeated node id calls etc -> pre-allocate etc.
        parsed = parse_packet(msg)
        if not parsed:
            return  # Return on dropped packages when runtime assertions don't apply -> ex. protocol version
        _version, _ptype, _src, _dst, _seq, _ttl, _flags, _plen, _payload = parsed

        my_id = self.node_id()

        logger().debug(f"RX packet dst={_dst}, me={my_id}")

        # Return if packet is from self
        if _src == my_id:
            return

        key = (_src, _seq)
        # DROP duplicates if not partial
        if not (_flags & MESH_FLAG_PARTIAL) and self._seen(*key):
            return

        if _flags & MESH_FLAG_GATEWAY:
            self.device_registry(host, _src, _version, _seq, True)

        else:
            self.device_registry(host, _src, _version, _seq, False)

        # packet type check

        if _ptype == MESH_TYPE_HELLO:
            logger().debug("HELLO packet received")

            if _flags & MESH_FLAG_ACK:
                await self.async_hello_ack(host)
                logger().debug("HELLO_ACK sent")
                return

        if _ptype == MESH_TYPE_HELLO_ACK and _dst == my_id:
            logger().debug("HELLO_ACK packet received")

            neighbors = decode_neighbour_bytes(_payload)
            logger().debug(f"Neighbors: {neighbors}")
            for n in neighbors:
                self._add_received_neighbor(
                    *self.process_route_entry(_src, host, tuple(n))
                )
            return

        # FORWARD if not for us and not Broadcast
        if (
            _dst != my_id
            and _dst != BROADCAST_ADDR
            and _ptype in (MESH_TYPE_DATA, MESH_TYPE_HELLO_ACK)
        ):
            logger().debug("Forwarding")
            if _ttl > 1:
                _ttl -= 1

                fwd_packet = build_packet(
                    _ptype, _src, _dst, _seq, _ttl, _flags, _payload
                )

                # broadcast forward (simple flooding)
                self._esp.send(self.target(_dst), fwd_packet, False)

            return

        if _ptype == MESH_TYPE_DATA:
            logger().debug("DATA packet received")

            idx = _payload[0]
            total = _payload[1]
            data = _payload[2:]

            if _flags & MESH_FLAG_PARTIAL_START:
                self._fragments[key] = [None] * total

            if key not in self._fragments:
                return

            frags = self._fragments[key]
            frags[idx] = data

            if not (_flags & MESH_FLAG_PARTIAL_END):
                return

            # check completeness
            for f in frags:
                if f is None:
                    return

            # build final payload efficiently
            total_len = sum(len(f) for f in frags)
            full = bytearray(total_len)

            pos = 0
            for f in frags:
                l = len(f)
                full[pos : pos + l] = f
                pos += l

            del self._fragments[key]
            _payload = full

            try:
                # (mac,node_id),(_payload)
                if not self._raw_recv_callback_data:
                    _payload = _payload.decode("utf-8")
                if self._on_recv:
                    await self._on_recv((host, _src), _payload)
            except TypeError as e:
                logger().error(
                    "Hint: Mesh callback must be async and use 'async def'"
                    "Note: ensure the function contains at least one 'await' "
                    "(e.g. 'await asyncio.sleep(0)') to avoid blocking the scheduler."
                )
                logger().error(f"Original Mesh receive error: {e}")
            except Exception as e:
                logger().error(f"Mesh receive error in callback: {e}")

    def _hello(self) -> tuple[bytearray, bytes]:
        """
        Build a hello packet.
        :return:  (packet,addr)
        """

        # Increment sequence number
        self._up_sequence()

        # Build hello packet
        return build_packet(
            MESH_TYPE_HELLO,
            self.node_id(),
            BROADCAST_ADDR,
            self._sequence,
            self._ttl,
            MESH_FLAG_BCAST | MESH_FLAG_ACK,
            b"",
            self._gateway,
        ), BROADCAST_ADDR_MAC

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

    def _hello_ack(
        self, mac: bytes | bytearray
    ) -> tuple[int, int, int, int, int, int, bytes, bool]:
        """
        Build the hello_ack packet.

        :param mac:
        :returns: the packet as tuple
        """
        _payload = encode_neighbour_tuple(self._neighbors)
        logger().debug(f"HELLO_ACK _payload: {_payload}")

        self._up_sequence()

        return (
            MESH_TYPE_HELLO_ACK,
            self.node_id(),
            self.node_id(mac),
            self._sequence,
            self._ttl,
            0,
            _payload,
            self._gateway,
        )

    def hello_ack(self, mac: bytes | bytearray) -> None:
        """
        Send a hello ack packet.
        :param mac:
        :return:
        """
        _pkt = self._hello_ack(mac)

        for _p in chunk_packet(*_pkt):
            logger().debug("Sending chunk...")
            self._send(_p, mac, False)

    async def async_hello_ack(self, mac: bytes | bytearray) -> None:
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

    async def async_wait_for_hello_ack(
        self, node_id: int, timeout: float = 5.0
    ) -> bool:
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

    def send_data(
        self,
        dst_node_id: int,
        payload: str | bytearray | bytes,
        not_found_error: bool = False,
    ) -> None:
        """
        Send a data packet/packets.
        :param dst_node_id: The target which the message should be sent to.
        :param payload:
        :param not_found_error: Weather to throw an error if target is unavailable. If off at this case it is Broadcasted.
        :return:
        """

        _mac = self.target(dst_node_id, not_found_error)
        self._up_sequence()
        for _p in chunk_packet(
            MESH_TYPE_DATA,
            self.node_id(),
            dst_node_id,
            self._sequence,
            self._ttl,
            MESH_FLAG_UNICAST,
            payload,
            self._gateway,
        ):
            self._send(_p, _mac, True)

    async def async_send_data(
        self,
        dst_node_id: int,
        payload: str | bytearray | bytes,
        not_found_error: bool = False,
    ) -> None:
        """
        Send a data packet/packets.
        :param dst_node_id:
        :param payload:
        :param not_found_error: Weather to throw an error if target is unavailable. If off at this case it is Broadcasted.
        :return:
        """
        _mac = self.target(dst_node_id, not_found_error)

        for _p in chunk_packet(
            MESH_TYPE_DATA,
            self.node_id(),
            dst_node_id,
            self._sequence,
            self._ttl,
            MESH_FLAG_UNICAST,
            payload,
            self._gateway,
        ):
            await self._async_send(_p, _mac, True)

    # Mesh Runtime section -----------------------------------------------------------

    def start(self) -> None:
        """
        Start the mesh.
        This will initialize the ESPNow and add the broadcast peer.
        :return:
        """
        logger().debug(f"START CALLED {self._started}, {self._starting}")
        if self._started or self._starting:
            return

        self._starting = True

        try:
            gc.collect()

            if self._wlan is None:
                self._wlan = WLAN(STA_IF)

            if not self._wlan.active():
                self._wlan.active(True)
                self._wlan.disconnect()
                self._wlan.config(
                    channel=ESPNOW_WIFI_CHANNEL, txpower=ESPNOW_WIFI_TXPOWER
                )

            if self._esp is None:
                self._esp = AIOESPNow()
                self._esp.active(True)
                # self._esp.config(rxbuf=4)

            _conf = get_config()
            _secret = _conf.get(MESH_SECRET)

            if _secret is not None:
                time.sleep_ms(200)
                self._update_pmk(str(_secret))

            self._add(BROADCAST_ADDR_MAC)

            self._started = True
            self.node_id()  # Important <-- force setting id

        finally:
            self._starting = False

    def stop(self):
        if not self._started:
            return

        self.rx_disable()

        if self._esp:
            self._esp.active(False)
            self._esp = None

        if self._wlan:
            self._wlan.active(False)
            self._wlan = None

        self._receiving = False
        self._started = False

        gc.collect()

    def rx_enable(self, listen_ms: int | None = None):
        """
        Enable packet reception.

        Automatically starts the mesh (calls 'mesh().start()') if it has not
        been started yet.

        :param listen_ms: Optional duration in milliseconds to keep reception
                          enabled. If None, reception remains enabled indefinitely.
        :return: None
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
        Register an async callback function to be called when a packet is received.
        Note: The callback function should have the signature: callback(host, msg)
        or callback(*args).

        - host: tuple -> (MAC,node_id)
        - msg: bytes|bytearray -> payload

        :param callback:
        :param raw: Whether the payload should automatically be decoded (utf-8) or not -> false == decoded
        :return:
        """
        self._raw_recv_callback_data = raw
        self._on_recv = callback

    async def receive_task(self):
        """
        This is the reception task. (DEPRECATED)
        :return:
        """
        if not self._started:
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

    async def run(self):
        """
        Unified mesh loop:
        - receive packets
        - send HELLO (heartbeat)
        - cleanup neighbors

        Timing:
        - HELLO: every MESH_HELLO_INTERVAL ms (with node_id jitter)
        - CLEAN: every MESH_CLEAN_INTERVAL ms

        RX:
        - host: tuple -> (MAC, node_id)
        - msg: bytes|bytearray
        - handled via self._irq(host, msg)

        Notes:
        - non-blocking RX (airecv)
        - uses ticks_ms (wrap-safe)
        - errors logged, loop continues
        - auto-start if not started

        :return: None
        """

        if not self._started:
            self.start()

        # pre-allocate to save lookup time
        _ticks_diff = time.ticks_diff
        _ticks_ms = time.ticks_ms
        _sleep_ms = asyncio.sleep_ms
        _airecv = self._esp.airecv
        _async_hello = self.async_hello
        _clean_neighbors = self._cleanup_neighbors

        now = _ticks_ms()

        last_hello = now - (
            self.node_id() % 2000
        )  # not just time but with jitter -> not all at the same time -> collision
        last_clean = now

        while True:
            now = _ticks_ms()

            # Receive
            if self._rx_enabled:
                try:
                    host, msg = await _airecv()
                    if host and msg:
                        await self._irq(host, msg)
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger().error(f"mesh rx error: {e}")

            # Hello
            if _ticks_diff(now, last_hello) > MESH_HELLO_INTERVAL:
                await _async_hello()
                last_hello = now

            # Clean
            if _ticks_diff(now, last_clean) > MESH_CLEAN_INTERVAL:
                _clean_neighbors()
                last_clean = now

            # yield
            await _sleep_ms(5)

    # Information section --------------------------------------------------------------------------------

    def stats(self):
        """
        Return mesh statistics.
        :return: (tx_pkts, tx_responses, tx_failures, rx_packets, rx_dropped_packets, started, receiving, node_id, MAC, sequence, registered_neighbors_count)
        """
        return (
            self._esp.stats(),
            self._started,
            self._receiving,
            self._node_id,
            self._wlan.config("mac"),
            self._sequence,
            len(self._neighbors),
        )


_mesh: Mesh | None = None


def mesh() -> Mesh:
    """
    This returns the Mesh instance.
    :return:
    """
    global _mesh
    if _mesh is None:
        _mesh = Mesh()
    return _mesh


def mesh_callback(raw: bool = False):
    """
    Decorator to set the mesh callback function.
    Register an async callback function to be called when a packet is received.

    Note: The callback function should have the signature: callback(host, msg) or callback(*args).

    - More info on https://pauwol.github.io/PicoCore/api/overview/ #TODO: Change to right URL.
    - host: tuple -> (mac,node_id)
    - msg: bytes|bytearray -> payload

    :param raw: Whether the payload should automatically be decoded (utf-8) or not -> false == decoded

    :return:
    """

    def deco(fn):
        mesh().callback(fn, raw)
        return fn

    return deco

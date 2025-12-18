"""
Fast, compact CRC-8 (poly=0x07) for MicroPython
Table-based default (256 bytes table) -> best perf.
Optional table-less mode available for extremely low RAM.
"""


_DEFAULT_POLY = 0x07
_DEFAULT_INIT = 0x00

def _make_table(poly: int = _DEFAULT_POLY) -> bytearray:
    """
    Table generation (fast; done once on import)
    :param poly:
    :return:
    """
    t = bytearray(256)
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
        t[i] = crc
    return t

# Precompute table (occupies ~256 bytes RAM) - recommended.
_TABLE = _make_table(_DEFAULT_POLY)

def crc8(data: bytes|bytearray|memoryview,
         init: int = _DEFAULT_INIT,
         table: bytearray = _TABLE
         ):
    """
    Compute CRC8 over bytes-like `data`.
    `data` can be bytes, bytearray, memoryview, or list/tuple of ints.
    Returns int 0..255.
    """
    crc = init & 0xFF
    # memoryview avoids extra allocations and is fast in MicroPython
    if isinstance(data,memoryview):
        mv = data
    else:
        mv = memoryview(data)

    tbl = table
    for b in mv:
        # XOR then table lookup
        crc = tbl[crc ^ b]
    return crc


def crc8_update(crc: int, data: bytes|bytearray, table: bytearray = _TABLE) -> int:
    """
    Continue CRC8 with existing `crc` value.
    Returns updated crc.
    """
    crc &= 0xFF
    mv = memoryview(data)
    tbl = table
    for b in mv:
        crc = tbl[crc ^ b]
    return crc


# --- Table-less (bitwise) fallback for extremely low RAM ---
def crc8_nontable(data: bytes|bytearray,
                  poly: int = _DEFAULT_POLY,
                  init: int = _DEFAULT_INIT
                  ) -> int:
    """
    CRC-8 without table. Much less RAM, slower CPU.
    Use when you cannot afford the 256-byte table.
    """
    crc = init & 0xFF
    mv = memoryview(data)
    for b in mv:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


# --- Class API (streaming) ---
class CRC8:
    """
    Streaming CRC8 object.
    CRC8(use_table=True) -> fast (uses shared table)
    CRC8(use_table=False) -> uses bitwise (no table memory)
    """
    __slots__ = ("_crc", "_init", "_use_table", "_table", "_poly")

    def __init__(self,
                 poly: int = _DEFAULT_POLY,
                 init: int = _DEFAULT_INIT,
                 use_table: bool = True
                 ):
        """
        Initialize CRC8 object.
        :param poly:
        :param init:
        :param use_table:
        """
        self._init = init & 0xFF
        self._crc = self._init
        self._use_table = bool(use_table)
        self._poly = poly & 0xFF
        self._table = _TABLE if (use_table and poly == _DEFAULT_POLY) \
            else (_make_table(poly) if use_table else None)

    @property
    def crc8(self) -> int:
        """
        Return the CRC8 value.
        :return: int
        """
        return self._crc

    @crc8.setter
    def crc8(self,value: int) -> None:
        """
        Set the CRC8 value.
        :param value: int
        :return: None
        """
        self._crc = value

    def update(self, data:bytes|bytearray) -> None:
        """
        Update CRC8 with new data.
        :param data:
        """
        if self._use_table:
            tbl = self._table
            crc = self._crc
            for b in memoryview(data):
                crc = tbl[crc ^ b]
            self._crc = crc
        else:
            crc = self._crc
            poly = self._poly
            for b in memoryview(data):
                crc ^= b
                for _ in range(8):
                    if crc & 0x80:
                        crc = ((crc << 1) ^ poly) & 0xFF
                    else:
                        crc = (crc << 1) & 0xFF
            self._crc = crc

    def digest(self) -> int:
        """
        Return the CRC8 value.
        :return:
        """
        return self._crc & 0xFF

    def reset(self) -> None:
        """
        Reset CRC8 to initial value.
        :return:
        """
        self._crc = self._init

    def copy(self) -> "CRC8":
        """
        Return a copy of the CRC8 object.
        :return:
        """
        c = CRC8(poly=self._poly, init=self._init, use_table=self._use_table)
        c.crc8 = self._crc
        return c


def append_crc8_to_bytes(buf:bytes|bytearray) -> bytes:
    """
    Returns a new bytes object = buf + crc8(buf).
    (Convenient for short headers.)
    :param buf:
    :return:
    """
    c = crc8(buf)
    return bytes(buf) + bytes([c])


def append_crc8_to_bytearray(buf:bytearray) -> int:
    """
    Appends crc to a bytearray in-place (efficient).
    :param buf:
    :return:
    """
    c = crc8(buf)
    buf.append(c)
    return c


def verify_crc8(data_with_crc:bytes|bytearray) -> bool:
    """
    Verify last byte is CRC8 of preceding bytes.
    :param data_with_crc:
    :return:
    """
    if len(data_with_crc) < 1:
        return False
    mv = memoryview(data_with_crc)
    # last byte:
    expected = mv[-1]
    crc = crc8(mv[:-1])
    return crc == expected

# Fast, compact CRC-8 (poly=0x07) for MicroPython
# Table-based default (256 bytes table) -> best perf.
# Optional table-less mode available for extremely low RAM.

_DEFAULT_POLY = 0x07
_DEFAULT_INIT = 0x00

# --- Table generation (fast; done once on import) ---
def _make_table(poly=_DEFAULT_POLY):
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


# --- Simple functional API (fast) ---
def crc8(data, init=_DEFAULT_INIT, table=_TABLE):
    """
    Compute CRC8 over bytes-like `data`.
    `data` can be bytes, bytearray, memoryview, or list/tuple of ints.
    Returns int 0..255.
    """
    crc = init & 0xFF
    # memoryview avoids extra allocations and is fast in MicroPython
    mv = memoryview(data)
    tbl = table
    for b in mv:
        # XOR then table lookup
        crc = tbl[crc ^ b]
    return crc


def crc8_update(crc, data, table=_TABLE):
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
def crc8_nontable(data, poly=_DEFAULT_POLY, init=_DEFAULT_INIT):
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

    def __init__(self, poly=_DEFAULT_POLY, init=_DEFAULT_INIT, use_table=True):
        self._init = init & 0xFF
        self._crc = self._init
        self._use_table = bool(use_table)
        self._poly = poly & 0xFF
        self._table = _TABLE if use_table and poly == _DEFAULT_POLY else (_make_table(poly) if use_table else None)

    def update(self, data):
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

    def digest(self):
        return self._crc & 0xFF

    def reset(self):
        self._crc = self._init

    def copy(self):
        c = CRC8(poly=self._poly, init=self._init, use_table=self._use_table)
        c._crc = self._crc
        return c


# --- Convenience helpers for packet operations ---
def append_crc8_to_bytes(buf):
    """
    Returns a new bytes object = buf + crc8(buf).
    (Convenient for short headers.)
    """
    c = crc8(buf)
    return bytes(buf) + bytes([c])


def append_crc8_to_bytearray(buf):
    """
    Appends crc to a bytearray in-place (efficient).
    """
    c = crc8(buf)
    buf.append(c)
    return c


def verify_crc8(data_with_crc):
    """
    Verify last byte is CRC8 of preceding bytes.
    Returns True/False.
    """
    if len(data_with_crc) < 1:
        return False
    mv = memoryview(data_with_crc)
    # last byte:
    expected = mv[-1]
    crc = crc8(mv[:-1])
    return crc == expected

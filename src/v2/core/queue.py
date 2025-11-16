try:
    import machine
    def _disable_irq():
        return machine.disable_irq()
    def _enable_irq(state):
        machine.enable_irq(state)
except Exception:
    # machine may not exist (e.g. running on PC for tests)
    def _disable_irq():
        return None
    def _enable_irq(_):
        return None

class RingBuffer:
    """
    General-purpose ring buffer for arbitrary Python objects.
    - capacity: maximum number of items stored
    - overwrite: if True, put() overwrites oldest item when full
    Methods: put, get, peek, clear, available, free, is_empty, is_full, to_list, extend
    """

    def __init__(self, capacity, overwrite=False):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._cap = int(capacity)
        self._buf = [None] * self._cap
        self._head = 0  # index for next write
        self._tail = 0  # index for next read
        self._count = 0
        self._overwrite = bool(overwrite)
        # mask optimization when capacity is power of two
        if (self._cap & (self._cap - 1)) == 0:
            self._mask = self._cap - 1
        else:
            self._mask = None

    def _inc(self, idx, step=1):
        if self._mask is not None:
            return (idx + step) & self._mask
        else:
            n = idx + step
            if n >= self._cap:
                n -= self._cap
            return n

    def put(self, item):
        """Push item. If full:
           - if overwrite=True, oldest item is dropped and new item stored
           - else raises IndexError
        """
        irq_state = _disable_irq()
        try:
            if self._count == self._cap:
                if not self._overwrite:
                    raise IndexError("RingBuffer full")
                # overwrite oldest: advance tail (drop one)
                self._tail = self._inc(self._tail)
                self._count -= 1
            self._buf[self._head] = item
            self._head = self._inc(self._head)
            self._count += 1
        finally:
            _enable_irq(irq_state)

    def put_list(self, items):
        for item in items:
            self.put(item)

    def get(self):
        """Pop and return oldest item. Raises IndexError if empty."""
        irq_state = _disable_irq()
        try:
            if self._count == 0:
                raise IndexError("RingBuffer empty")
            item = self._buf[self._tail]
            # help GC on memory-constrained ports
            self._buf[self._tail] = None
            self._tail = self._inc(self._tail)
            self._count -= 1
            return item
        finally:
            _enable_irq(irq_state)

    def peek(self, index=0):
        """Peek at item `index` (0 is oldest) without removing. Raises IndexError if out of range."""
        if index < 0 or index >= self._count:
            raise IndexError("peek index out of range")
        pos = self._tail
        # compute pos + index
        if self._mask is not None:
            pos = (pos + index) & self._mask
        else:
            pos += index
            if pos >= self._cap:
                pos -= self._cap
        return self._buf[pos]

    def peek_latest(self):
        """Return the newest (most recently added) item without removing it."""
        if self._count == 0:
            raise IndexError("peek from empty buffer")
        return self.peek(self._count - 1)

    def extend(self, iterable):
        """Push multiple items until the buffer is full (or all items consumed)."""
        for it in iterable:
            try:
                self.put(it)
            except IndexError:
                # buffer full and overwrite=False
                break

    def clear(self, keep_memory=False):
        """Clear buffer. If keep_memory is False, zero-out storage (helps GC)."""
        irq_state = _disable_irq()
        try:
            if not keep_memory:
                for i in range(self._cap):
                    self._buf[i] = None
            self._head = 0
            self._tail = 0
            self._count = 0
        finally:
            _enable_irq(irq_state)

    def available(self):
        """Number of items stored."""
        return self._count

    def free(self):
        """Remaining capacity."""
        return self._cap - self._count

    def is_empty(self):
        return self._count == 0

    def is_full(self):
        return self._count == self._cap

    def to_list(self):
        """Return elements in order as a list (allocates)."""
        out = []
        idx = self._tail
        for _ in range(self._count):
            out.append(self._buf[idx])
            idx = self._inc(idx)
        return out

    def __iter__(self):
        """Return iterator over elements in order."""
        idx = self._tail
        for _ in range(self._count):
            yield self._buf[idx]
            idx = self._inc(idx)

    def __len__(self):
        return self._count

    def __repr__(self):
        return "<RingBuffer cap={} items={}>".format(self._cap, self._count)


class ByteRingBuffer:
    """
    Ring buffer specialized for raw bytes (store 0-255 ints).
    - capacity: max number of bytes stored
    Methods similar to RingBuffer but works with bytes/ints and supports bulk put/get.
    """

    def __init__(self, capacity):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._cap = int(capacity)
        self._buf = bytearray(self._cap)
        self._head = 0
        self._tail = 0
        self._count = 0
        if (self._cap & (self._cap - 1)) == 0:
            self._mask = self._cap - 1
        else:
            self._mask = None

    def _inc(self, idx, step=1):
        if self._mask is not None:
            return (idx + step) & self._mask
        else:
            n = idx + step
            if n >= self._cap:
                n -= self._cap
            return n

    def put(self, data):
        """
        Put bytes or int.
        - if int: put single byte (0-255), raises IndexError if full.
        - if bytes/bytearray/iterable: put as many bytes as fit, returns number of bytes written.
        """
        irq_state = _disable_irq()
        wrote = 0
        try:
            if isinstance(data, int):
                if self._count == self._cap:
                    raise IndexError("ByteRingBuffer full")
                self._buf[self._head] = data & 0xFF
                self._head = self._inc(self._head)
                self._count += 1
                return 1
            # treat as bytes-like or iterable of ints
            for b in data:
                if self._count == self._cap:
                    break
                self._buf[self._head] = b & 0xFF
                self._head = self._inc(self._head)
                self._count += 1
                wrote += 1
            return wrote
        finally:
            _enable_irq(irq_state)

    def get(self, n=1):
        """
        Retrieve up to n bytes. Returns bytes object (may be shorter than requested
        if buffer didn't have enough). If n==1 returns a single int for speed?
        To keep API simple we return bytes always.
        """
        irq_state = _disable_irq()
        try:
            if self._count == 0:
                return b''
            if n <= 0:
                return b''
            if n > self._count:
                n = self._count
            # assemble result
            out = bytearray(n)
            for i in range(n):
                out[i] = self._buf[self._tail]
                self._tail = self._inc(self._tail)
                self._count -= 1
            return bytes(out)
        finally:
            _enable_irq(irq_state)

    def available(self):
        return self._count

    def free(self):
        return self._cap - self._count

    def clear(self):
        irq_state = _disable_irq()
        try:
            # zeroing not strictly necessary but helps deterministic state
            for i in range(self._cap):
                self._buf[i] = 0
            self._head = 0
            self._tail = 0
            self._count = 0
        finally:
            _enable_irq(irq_state)

    def is_empty(self):
        return self._count == 0

    def is_full(self):
        return self._count == self._cap

    def to_bytes(self):
        """Return contents in order as bytes (allocates)."""
        return b''.join(self.get(self._count) for _ in (0,)) if self._count else b''

    def __iter__(self):
        """Return iterator over elements in order."""
        idx = self._tail
        for _ in range(self._count):
            yield self._buf[idx]
            idx = self._inc(idx)

    def __len__(self):
        return self._count

    def __repr__(self):
        return "<ByteRingBuffer cap={} bytes={}>".format(self._cap, self._count)

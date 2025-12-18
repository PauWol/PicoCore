"""
PicoCore V2 Queue Module

This module provides a RingBuffer and ByteRingBuffer class
for a ring buffer of arbitrary Python objects and bytes.

Usage:
    from core.queue import RingBuffer, ByteRingBuffer

    rb = RingBuffer(10)
    rb.put(1)
    rb.put(2)
    rb.put(3)
    print(rb.get())
    print(rb.get())
    print(rb.get())
"""

import machine
def _disable_irq() -> object:
    return machine.disable_irq()
def _enable_irq(state: int) -> None:
    machine.enable_irq(state)



class RingBuffer:
    """
    General-purpose ring buffer for arbitrary Python objects.
    - capacity: maximum number of items stored
    - overwrite: if True, put() overwrites oldest item when full
    Methods: put, get, peek, clear, available, free, is_empty, is_full, to_list, extend
    """

    def __init__(self, capacity: int, overwrite: bool = False) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._cap = int(capacity)
        self._buf: list[object | None] = [None] * self._cap
        self._head = 0  # index for next write
        self._tail = 0  # index for next read
        self._count = 0
        self._overwrite = bool(overwrite)
        self._mask : int | None = None
        # mask optimization when capacity is power of two
        if (self._cap & (self._cap - 1)) == 0:
            self._mask = self._cap - 1
        else:
            self._mask = None

    def _inc(self, idx: int, step: int = 1) -> int:
        if self._mask is not None:
            return (idx + step) & self._mask

        n = idx + step
        if n >= self._cap:
            n -= self._cap
        return n

    def put(self, item: object) -> None:
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

    def put_index(self, index: int, item: object) -> None:
        """Insert item at specific index (0 is oldest).
        If index is out of bounds, raises IndexError.
        """
        if index < 0 or index > self._count:
            raise IndexError("Index out of range")

        irq_state = _disable_irq()
        try:
            # Calculate the actual position in the circular buffer
            pos = (self._tail + index) % self._cap

            # Insert the new item
            self._buf[pos] = item
        finally:
            _enable_irq(irq_state)

    def put_list(self, items: list[object]) -> None:
        """Push multiple items until the buffer is full (or all items consumed)."""
        for item in items:
            self.put(item)

    def get(self) -> object:
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

    def peek(self, index: int = 0) -> object:
        """Peek at item `index` (0 is oldest) without removing.
            Raises IndexError if out of range.
        """
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

    def peek_latest(self) -> object:
        """Return the newest (most recently added) item without removing it."""
        if self._count == 0:
            raise IndexError("peek from empty buffer")
        return self.peek(self._count - 1)

    def extend(self, iterable: list[object]) -> None:
        """Push multiple items until the buffer is full (or all items consumed)."""
        for it in iterable:
            try:
                self.put(it)
            except IndexError:
                # buffer full and overwrite=False
                break

    def clear(self, keep_memory: bool = False) -> None:
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

    def clear_index(self, index: int) -> None:
        """Remove item at index (0 is oldest).
        If index is out of bounds, raises IndexError.
        """
        if index < 0 or index >= self._count:
            raise IndexError("Index out of range")

        irq_state = _disable_irq()
        try:
            # Shift elements to fill the gap
            for i in range(index, self._count - 1):
                curr_pos = (self._tail + i) % self._cap
                next_pos = (self._tail + i + 1) % self._cap
                self._buf[curr_pos] = self._buf[next_pos]

            # Clear the last position and update pointers
            last_pos = (self._tail + self._count - 1) % self._cap
            self._buf[last_pos] = None
            self._count -= 1

            # Update head pointer
            self._head = (self._head - 1) % self._cap if self._count > 0 else 0
        finally:
            _enable_irq(irq_state)

    def available(self) -> int:
        """Number of items stored."""
        return self._count

    def free(self) -> int:
        """Remaining capacity."""
        return self._cap - self._count

    def is_empty(self) -> bool:
        """
        Whether the buffer is empty or not.
        :return: True if the buffer is empty, False otherwise.
        """
        return self._count == 0

    def is_full(self) -> bool:
        """
        Whether the buffer is full or not.
        :return: True if the buffer is full, False otherwise.
        """
        return self._count == self._cap

    def to_list(self) -> list[object]:
        """Return elements in order as a list (allocates)."""
        out: list[object] = []
        idx = self._tail
        for _ in range(self._count):
            out.append(self._buf[idx])
            idx = self._inc(idx)
        return out

    def __iter__(self): # type: ignore
        """Return iterator over elements in order."""
        idx = self._tail
        for _ in range(self._count):
            yield self._buf[idx]
            idx = self._inc(idx)

    def __len__(self) -> int:
        return self._count

    def __repr__(self) -> str:
        return f"<RingBuffer cap={self._cap} items={self._count}>"


class ByteRingBuffer:
    """
    Ring buffer specialized for raw bytes (store 0-255 ints).
    - capacity: max number of bytes stored
    Methods similar to RingBuffer but works with bytes/ints and supports bulk put/get.
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._cap = int(capacity)
        self._buf = bytearray(self._cap)
        self._head = 0
        self._tail = 0
        self._count = 0
        self._mask: int | None = None
        if (self._cap & (self._cap - 1)) == 0:
            self._mask = self._cap - 1
        else:
            self._mask = None

    def _inc(self, idx: int, step: int = 1) -> int:
        if self._mask is not None:
            return (idx + step) & self._mask

        n = idx + step
        if n >= self._cap:
            n -= self._cap
        return n

    def put(self, data: int | bytes | bytearray | list[int]) -> int:
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

    def get(self, n: int = 1) -> bytes:
        """
        Retrieve up to n bytes. Returns bytes object (maybe shorter than requested
        if buffer didn't have enough). If n==1 returns a single int for speed?
        To keep API simple we return bytes always.
        """
        irq_state = _disable_irq()
        try:
            if n <= 0 or self._count == 0:
                return b''

            n = min(n, self._count)

            # assemble result
            out = bytearray(n)
            for i in range(n):
                out[i] = self._buf[self._tail]
                self._tail = self._inc(self._tail)
                self._count -= 1
            return bytes(out)
        finally:
            _enable_irq(irq_state)

    def available(self) -> int:
        """
        How many bytes are in the buffer.
        :return: Returns the number of bytes that are in the buffer.
        """
        return self._count

    def free(self) -> int:
        """
        How much space is left in the buffer.
        :return: Returns the number of bytes that can be
                added to the buffer before it is full.
        """
        return self._cap - self._count

    def clear(self) -> None:
        """
        Clear the buffer.
        """
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

    def is_empty(self) -> bool:
        """
        Whether the buffer is empty or not.
        :return: True if the buffer is empty, False otherwise.
        """
        return self._count == 0

    def is_full(self) -> bool:
        """
        Whether the buffer is full or not.
        :return: True if the buffer is full, False otherwise.
        """
        return self._count == self._cap

    def to_bytes(self) -> bytes:
        """Return contents in order as bytes (allocates)."""
        return b''.join(self.get(self._count) for _ in (0,)) if self._count else b''

    def __iter__(self): # type: ignore
        """Return iterator over elements in order."""
        idx = self._tail
        for _ in range(self._count):
            yield self._buf[idx]
            idx = self._inc(idx)

    def __len__(self) -> int:
        return self._count

    def __repr__(self) -> str:
        return f"<ByteRingBuffer cap={self._cap} bytes={self._count}>"

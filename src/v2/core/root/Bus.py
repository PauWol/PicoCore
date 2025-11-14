class RingBuffer:
    def __init__(self, size=8):
        self._buf = [None] * size
        self._size = size
        self._start = 0
        self._count = 0

    def put(self, item):
        if self._count < self._size:
            idx = (self._start + self._count) % self._size
            self._buf[idx] = item
            self._count += 1
        else:
            # overwrite oldest
            self._buf[self._start] = item
            self._start = (self._start + 1) % self._size

    def get_all(self):
        out = []
        for i in range(self._count):
            out.append(self._buf[(self._start + i) % self._size])
        self._start = 0
        self._count = 0
        return out


class PubSub:
    """Tiny MicroPython pub/sub with ID-based unsubscribe."""

    def __init__(self):
        self._subs = []  # [(id, pattern, cb, buf)]
        self._next = 1

    def subscribe(self, pattern, cb=None, bufsize=0) -> tuple[int, RingBuffer | None]:
        buf = RingBuffer(bufsize) if bufsize > 0 else None
        sub_id = self._next
        self._next += 1
        self._subs.append((sub_id, pattern, cb, buf))
        return sub_id, buf

    def unsubscribe(self, id=None, topic=None, cb=None) -> None:
        """Unsubscribe by id, topic, or callback."""
        new = []
        for s in self._subs:
            sid, pat, f, b = s
            if id is not None and sid == id:
                continue
            if topic is not None and pat == topic and (cb is None or f == cb):
                continue
            if cb is not None and f == cb and topic is None and id is None:
                continue
            new.append(s)
        self._subs = new

    def publish(self, topic, msg) -> None:
        for sid, pat, cb, buf in self._subs:
            if self._match(pat, topic):
                if buf:
                    buf.put((topic, msg))
                if cb:
                    try:
                        cb(topic, msg)
                    except Exception:
                        pass  # ignore failed callbacks safely

    @staticmethod
    def _match(pat, topic) -> bool:
        """MQTT-style topic matching."""
        ps, ts = pat.split('/'), topic.split('/')
        for i, p in enumerate(ps):
            if p == '#':
                return True
            if i >= len(ts):
                return False
            if p != '+' and p != ts[i]:
                return False
        return len(ps) == len(ts)


# ---------- Global instance + helper functions ----------

_bus = PubSub()

def bus():
    global _bus
    return _bus

def on(topic):
    """
    Decorator to subscribe to a topic.

    - The topic can contain + or # wildcards.More info on https://pauwol.github.io/PicoCore/api/overview/ #TODO: Change to right URL.
    - The function should have the signature func(topic, message) or func(*args).
    :param topic:
    :return: """
    def deco(fn):
        _bus.subscribe(topic, fn)
        return fn
    return deco

def emit(topic, msg):
    """ Emit a message to a topic. """
    _bus.publish(topic, msg)

def off(topic=None, cb=None, id=None):
    _bus.unsubscribe(id=id, topic=topic, cb=cb)

def manual(topic: str, bufsize: int = 10) -> tuple[int, RingBuffer]:
    """
    Subscribe to a topic without providing a callback function.

    This is useful if you want to receive messages in a different
    thread or if you want to process the messages manually.

    :param topic: The topic to subscribe to
    :param bufsize: The size of the ring buffer
    :return: A tuple containing the subscription ID and a RingBuffer object
    """
    return  _bus.subscribe(topic, cb=None, bufsize=bufsize)


#TODO: Add async support!!!
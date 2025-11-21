"""
PicoCore V2 Event Bus

This is a simple pub/sub implementation with ID-based unsubscribe.
The bus is a global instance that can be used to subscribe to events and emit events.

"""

from ..queue import RingBuffer


class PubSub:
    """Tiny MicroPython pub/sub with ID-based unsubscribe."""

    def __init__(self):
        """
        Initialize the PubSub instance.
        """
        self._subs = []  # [(id, pattern, cb, buf)]
        self._next = 1

    def subscribe(self, pattern, cb=None, buf_size=0) -> tuple[int, RingBuffer | None]:
        buf = RingBuffer(buf_size) if buf_size > 0 else None
        sub_id = self._next
        self._next += 1
        self._subs.append((sub_id, pattern, cb, buf))
        return sub_id, buf

    def unsubscribe(self, _id=None, topic=None, cb=None) -> None:
        """Unsubscribe by id, topic, or callback."""
        new = []
        for s in self._subs:
            sid, pat, f, _ = s
            if _id is not None and sid == _id:
                continue
            if topic is not None and pat == topic and (cb is None or f == cb):
                continue
            if cb is not None and f == cb and topic is None and _id is None:
                continue
            new.append(s)
        self._subs = new

    def publish(self, topic, msg) -> None:
        for _, pat, cb, buf in self._subs:
            if self._match(pat, topic):
                if buf:
                    buf.put((topic, msg))
                if cb:
                    try:
                        cb(topic, msg)
                    except Exception: # pylint: disable=broad-exception-caught
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
            if p not in (ts[i],'+'):
                return False
        return len(ps) == len(ts)


# ---------- Global instance + helper functions ----------

_bus = PubSub()

def bus():
    """
    Get the global bus instance.
    """
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

def off(topic=None, cb=None, _id=None):
    """
    Unsubscribe from a topic. unsubscribe by id, topic, or callback.
    :param topic:
    :param cb:
    :param _id:
    :return:
    """
    _bus.unsubscribe(_id=_id, topic=topic, cb=cb)

def manual(topic: str, buf_size: int = 10) -> tuple[int, RingBuffer]:
    """
    Subscribe to a topic without providing a callback function.

    This is useful if you want to receive messages in a different
    thread or if you want to process the messages manually.

    :param topic: The topic to subscribe to
    :param buf_size: The size of the ring buffer
    :return: A tuple containing the subscription ID and a RingBuffer object
    """
    return  _bus.subscribe(topic, cb=None, buf_size=buf_size)


#TODO: Add async support!!!

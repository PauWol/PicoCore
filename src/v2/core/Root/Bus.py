
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
        items = []
        for i in range(self._count):
            items.append(self._buf[(self._start + i) % self._size])
        self._start = 0
        self._count = 0
        return items

class PubSub:
    def __init__(self):
        self._subs = []  # [(pattern, callback, buffer)]

    def subscribe(self, topic_pattern, callback=None, bufsize=0):
        """
        Subscribe to a topic.
        - topic_pattern: string with optional + or # wildcards
        - callback: function(topic, message)
        - bufsize: optional ring buffer for pull mode
        Returns: buffer reference (or None if bufsize=0)
        """
        buf = RingBuffer(bufsize) if bufsize > 0 else None
        self._subs.append((topic_pattern, callback, buf))
        return buf

    def unsubscribe(self, topic_pattern, callback=None):
        self._subs = [
            (p, cb, b)
            for (p, cb, b) in self._subs
            if not (p == topic_pattern and (callback is None or cb == callback))
        ]

    def publish(self, topic, message):
        for pattern, callback, buf in self._subs:
            if self._match(pattern, topic):
                if buf:
                    buf.put((topic, message))
                if callback:
                    try:
                        callback(topic, message)
                    except Exception:
                        # ignore bad callbacks for safety
                        pass

    def _match(self, pattern, topic):
        """MQTT-style matching (+ = one level, # = all sublevels)"""
        p_levels = pattern.split('/')
        t_levels = topic.split('/')

        for i, p in enumerate(p_levels):
            if p == '#':
                return True
            if i >= len(t_levels):
                return False
            if p == '+':
                continue
            if p != t_levels[i]:
                return False
        return len(t_levels) == len(p_levels)

bus_instance = PubSub()

def bus():
    global bus_instance
    if not bus_instance:
        bus_instance = PubSub()
    return bus_instance
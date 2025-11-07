# core/utils/queue.py
# MicroPython-friendly ByteQueue + QueueManager
# Avoids typing & loging modules so it works on boot

# NOTE: flush_cb will be called with a bytes object when the queue is flushed.
# Keep flush_cb small and fast (no heavy I/O inside if possible).

class ByteQueue:
    def __init__(self, max_size=64, flush_cb=None, flush_trigger_size=None):
        # normalize/validate sizes
        if max_size is None:
            max_size = 64
        try:
            max_size = int(max_size)
        except Exception:
            raise ValueError("max_size must be integer-compatible")
        if max_size <= 0:
            raise ValueError("max_size must be > 0")
        self.max_size = max_size

        if flush_trigger_size is None:
            self.flush_trigger_size = self.max_size
        else:
            try:
                ft = int(flush_trigger_size)
                self.flush_trigger_size = ft if ft > 0 else self.max_size
            except Exception:
                self.flush_trigger_size = self.max_size

        self.buffer = bytearray()
        self.flush_cb = flush_cb

    def put(self, data):
        # accept bytes, bytearray or str
        if isinstance(data, str):
            try:
                data = data.encode("utf-8")
            except Exception:
                data = bytes(data)
        elif isinstance(data, bytearray):
            data = bytes(data)
        elif not isinstance(data, (bytes, bytearray)):
            raise TypeError("ByteQueue.put expects bytes/bytearray/str")

        data_len = len(data)
        buf_len = len(self.buffer)

        # if single chunk bigger than max_size: flush and raise
        if data_len > self.max_size:
            # try to flush existing buffer
            if self.flush_cb and buf_len:
                try:
                    self.flush_cb(bytes(self.buffer))
                except Exception:
                    # swallow callback exceptions to avoid crashing the system at logger time
                    pass
                self.buffer = bytearray()
            raise ValueError("Data too large for queue (size {})".format(data_len))

        # if adding would overflow, flush existing buffer first
        if buf_len + data_len > self.max_size:
            if self.flush_cb and buf_len:
                try:
                    self.flush_cb(bytes(self.buffer))
                except Exception:
                    pass
                self.buffer = bytearray()

        # append
        self.buffer.extend(data)

        # auto-flush when threshold reached
        if self.flush_trigger_size is not None and len(self.buffer) >= self.flush_trigger_size:
            self.flush()

    def flush(self):
        if self.flush_cb and self.buffer:
            try:
                self.flush_cb(bytes(self.buffer))
            except Exception:
                # swallow exceptions from callback to keep logger robust on device
                pass
        self.buffer = bytearray()

    def clear(self):
        self.buffer = bytearray()


class QueueManager:
    def __init__(self):
        self.queues = {}

    def register(self, name, max_size=64, flush_cb=None, flush_trigger_size=None):
        if not isinstance(name, str) or not name:
            raise ValueError("Queue name must be a non-empty string")
        q = ByteQueue(max_size=max_size, flush_cb=flush_cb, flush_trigger_size=flush_trigger_size)
        self.queues[name] = q

    def put(self, name, data):
        if name not in self.queues:
            # raising here is OK; alternatively you could silently create a queue
            raise KeyError("Queue not registered: {}".format(name))
        self.queues[name].put(data)

    def flush(self, name):
        if name in self.queues:
            self.queues[name].flush()

    def flush_all(self):
        for q in self.queues.values():
            q.flush()

    def clear(self, name):
        if name in self.queues:
            self.queues[name].clear()

"""
PicoCore V2 Event Bus

Improvements over V1:
- O(1) exact-topic dispatch via dict bucketing (no full-list scan for common case)
- Pre-split wildcard patterns at subscribe time — zero allocation in _match()
- Explicit is_async flag on callbacks — no iscoroutine() probing at runtime
- sync publish()  → sync cbs inline,  async cbs scheduled via create_task()
- async async_publish() → sync cbs inline, async cbs awaited in order
- In-place unsubscribe (reverse-index pop) — no full list rebuild
- IRQ-guarded structural mutations (subscribe / unsubscribe)
- Optional err_cb hook for failed callbacks — no more silent swallowing
- 16-bit ID rollover guard
- overwrite support forwarded to RingBuffer in manual()
- @on decorator stores sub_id on fn._sub_id for later off(_id=fn._sub_id)
"""

import machine
from uasyncio import create_task
from core.queue import RingBuffer


# ---------------------------------------------------------------------------
# IRQ helpers (mirrors queue.py convention)
# ---------------------------------------------------------------------------


def _dis() -> int:
    return machine.disable_irq()


def _en(state: int) -> None:
    machine.enable_irq(state)


# ---------------------------------------------------------------------------
# Internal subscription record
# ---------------------------------------------------------------------------


class _Sub:
    """
    Single subscription entry.  Using __slots__ keeps memory tight and avoids
    per-instance __dict__ overhead on MicroPython.
    """

    __slots__ = ("id", "parts", "cb", "buf", "is_async")

    def __init__(self, sub_id: int, parts, cb, buf, is_async: bool) -> None:
        self.id = sub_id  # unique int identifier
        self.parts = parts  # pre-split tuple for wildcards, None for exact
        self.cb = cb  # callable or None
        self.buf = buf  # RingBuffer or None
        self.is_async = is_async  # True  → cb is  async def, must be await-ed


# ---------------------------------------------------------------------------
# PubSub core
# ---------------------------------------------------------------------------


class PubSub:
    """
    Pub/sub event bus with bucketed dispatch and explicit async support.

    Subscription storage:
        _exact    dict[topic_str -> list[_Sub]]   — O(1) lookup, no pattern matching
        _wildcard list[_Sub]                      — only scanned when topic has + / #
                                                    (usually a very short list)
    """

    _ID_MAX: int = 0xFFFF  # 16-bit ceiling; wraps to 1 on overflow

    def __init__(self, err_cb=None) -> None:
        """
        :param err_cb: Optional callable(sub_id, topic, exc) invoked when a sync
                       callback raises.  Async callback errors are also forwarded here
                       when using async_publish().  If None, errors are dropped.
        """
        self._exact: dict = {}  # str -> list[_Sub]
        self._wildcard: list = []  # list[_Sub]  (wildcards only)
        self._next: int = 1
        self._err_cb = err_cb

    # ------------------------------------------------------------------
    # ID management
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        sid = self._next
        self._next = (self._next % self._ID_MAX) + 1
        return sid

    # ------------------------------------------------------------------
    # Pattern helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_wildcard(pattern: str) -> bool:
        return "+" in pattern or "#" in pattern

    @staticmethod
    def _match(pat_parts: tuple, topic_parts: tuple) -> bool:
        """
        MQTT-style matching.  Both arguments are pre-split tuples — no allocation
        happens here during a publish call.
        """
        lp = len(pat_parts)
        lt = len(topic_parts)
        for i in range(lp):
            p = pat_parts[i]
            if p == "#":
                return True  # # matches anything that follows, including nothing
            if i >= lt:
                return False
            if p != "+" and p != topic_parts[i]:
                return False
        return lp == lt

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        pattern: str,
        cb=None,
        buf_size: int = 0,
        is_async: bool = False,
        overwrite: bool = False,
    ) -> tuple:
        """
        Subscribe to a topic pattern.

        :param pattern:   MQTT-style topic.  May contain + or # wildcards.
        :param cb:        Callback callable(topic, msg).
                          Pass None for buffer-only (manual polling) subscribers.
        :param buf_size:  If > 0 a RingBuffer is created for manual polling.
        :param is_async:  MUST be True when cb is defined with `async def`.
                          Never auto-detected — caller is responsible.
        :param overwrite: Forwarded to RingBuffer(overwrite=) when buf_size > 0.
        :return:          (sub_id: int, buf: RingBuffer | None)
        """
        buf = RingBuffer(buf_size, overwrite) if buf_size > 0 else None

        irq = _dis()
        try:
            sid = self._next_id()
            if self._has_wildcard(pattern):
                parts = tuple(pattern.split("/"))  # split once, stored for lifetime
                sub = _Sub(sid, parts, cb, buf, is_async)
                self._wildcard.append(sub)
            else:
                sub = _Sub(sid, None, cb, buf, is_async)
                bucket = self._exact.get(pattern)
                if bucket is None:
                    self._exact[pattern] = [sub]
                else:
                    bucket.append(sub)
        finally:
            _en(irq)

        return sid, buf

    def unsubscribe(self, _id=None, topic: str = None, cb=None) -> None:
        """
        Remove subscriptions matching ANY of the supplied criteria.
        Uses reverse-index in-place pop — no full-list rebuild.

        :param _id:   Remove the subscription with this ID.
        :param topic: Remove subscriptions on this exact pattern string.
        :param cb:    Remove subscriptions whose callback is this object.
        """
        if _id is None and topic is None and cb is None:
            return  # nothing to do

        irq = _dis()
        try:
            # --- exact bucket(s) ---
            if topic is not None and not self._has_wildcard(topic):
                # fast path: only touch the one relevant bucket
                bucket = self._exact.get(topic)
                if bucket is not None:
                    self._prune(bucket, _id, cb)
                    if not bucket:
                        del self._exact[topic]
            else:
                # must scan every bucket (id- or cb-only removal, or wildcard topic filter)
                for key in list(self._exact.keys()):
                    bucket = self._exact[key]
                    self._prune(bucket, _id, cb)
                    if not bucket:
                        del self._exact[key]

            # --- wildcard list ---
            i = len(self._wildcard) - 1
            while i >= 0:
                s = self._wildcard[i]
                if self._matches_filter(s, _id, cb):  # noqa: SIM102
                    # if a topic filter was supplied, also check the pattern string
                    if topic is None or "/".join(s.parts) == topic:
                        self._wildcard.pop(i)
                i -= 1
        finally:
            _en(irq)

    @staticmethod
    def _prune(bucket: list, _id, cb) -> None:
        """In-place reverse removal from a bucket list."""
        i = len(bucket) - 1
        while i >= 0:
            if PubSub._matches_filter(bucket[i], _id, cb):
                bucket.pop(i)
            i -= 1

    @staticmethod
    def _matches_filter(s: _Sub, _id, cb) -> bool:
        if _id is not None and s.id == _id:
            return True
        return bool(cb is not None and s.cb is cb)

    # ------------------------------------------------------------------
    # Dispatch helpers (avoid code duplication between publish paths)
    # ------------------------------------------------------------------

    def _call_sync(self, sub: _Sub, topic: str, msg) -> None:
        """Invoke a synchronous callback with error forwarding."""
        try:
            sub.cb(topic, msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if self._err_cb:
                self._err_cb(sub.id, topic, exc)

    def _deliver(self, sub: _Sub, topic: str, msg) -> object:
        """
        Deliver one message to one subscriber (sync path).

        Puts into buffer if present.
        Sync  callbacks are called immediately.
        Async callbacks: returns the coroutine so the caller can schedule it.
        """
        if sub.buf is not None:
            sub.buf.put((topic, msg))
        if sub.cb is not None:
            if sub.is_async:
                return sub.cb(topic, msg)  # ← coroutine, NOT awaited yet
            self._call_sync(sub, topic, msg)
        return None

    async def _deliver_async(self, sub: _Sub, topic: str, msg) -> None:
        """
        Deliver one message to one subscriber (async path).

        Sync  callbacks are still called inline (non-blocking).
        Async callbacks are awaited.
        """
        if sub.buf is not None:
            sub.buf.put((topic, msg))
        if sub.cb is not None:
            if sub.is_async:
                try:
                    await sub.cb(topic, msg)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if self._err_cb:
                        self._err_cb(sub.id, topic, exc)
            else:
                self._call_sync(sub, topic, msg)

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, topic: str, msg) -> None:
        """
        Synchronous publish.

        - Sync  callbacks: called inline before publish() returns.
        - Async callbacks: each coroutine is handed to create_task().
                           Requires the uasyncio event loop to be running.
                           Do NOT use async subscribers for pre-loop events.
        - Buffer subs:     message appended to RingBuffer immediately.
        """
        topic_parts = None  # lazy — only split if wildcard subs exist

        # O(1) exact-match lookup
        bucket = self._exact.get(topic)
        if bucket:
            for sub in bucket:
                coro = self._deliver(sub, topic, msg)
                if coro is not None:
                    create_task(coro)

        # wildcard scan (typically very short)
        if self._wildcard:
            topic_parts = tuple(topic.split("/"))
            for sub in self._wildcard:
                if self._match(sub.parts, topic_parts):
                    coro = self._deliver(sub, topic, msg)
                    if coro is not None:
                        create_task(coro)

    async def async_publish(self, topic: str, msg) -> None:
        """
        Async publish — awaits async callbacks in subscription order.

        Use from within an async Root task when you need async callbacks to
        complete before execution continues past this call.
        Sync callbacks are still called inline; no create_task() overhead.
        """
        topic_parts = None

        bucket = self._exact.get(topic)
        if bucket:
            for sub in bucket:
                await self._deliver_async(sub, topic, msg)

        if self._wildcard:
            topic_parts = tuple(topic.split("/"))
            for sub in self._wildcard:
                if self._match(sub.parts, topic_parts):
                    await self._deliver_async(sub, topic, msg)


# ---------------------------------------------------------------------------
# Global singleton + module-level helper functions
# ---------------------------------------------------------------------------

_bus = PubSub()


def bus() -> PubSub:
    """Return the global PubSub instance."""
    return _bus


def on(topic: str, is_async: bool = False):
    """
    Decorator — subscribe a function to a topic.

    :param topic:    MQTT-style pattern.  May contain + or # wildcards.
    :param is_async: Set True when decorating an `async def` function.
                     Must be set explicitly — never auto-detected.

    The subscription ID is stored as fn._sub_id so you can later call:
        off(_id=my_handler._sub_id)

    Examples::

        @on('sensors/temp')
        def handle_temp(topic, msg): ...

        @on('sensors/+/alert', is_async=True)
        async def handle_alert(topic, msg):
            await do_something(msg)
    """

    def deco(fn):
        sid, _ = _bus.subscribe(topic, fn, is_async=is_async)
        fn._sub_id = sid
        return fn

    return deco


def emit(topic: str, msg) -> None:
    """
    Synchronous emit.
    Sync callbacks run inline; async callbacks are scheduled via create_task().
    """
    _bus.publish(topic, msg)


async def async_emit(topic: str, msg) -> None:
    """
    Async emit — awaits async callbacks in order.
    Must be called from within an async context (e.g. a Root task).
    """
    await _bus.async_publish(topic, msg)


def off(topic: str = None, cb=None, _id: int = None) -> None:
    """
    Unsubscribe.  Supply one or more of the keyword arguments.

    :param topic: Pattern string to match subscriptions against.
    :param cb:    Callback reference to remove.
    :param _id:   Subscription ID returned by subscribe() / stored as fn._sub_id.
    """
    _bus.unsubscribe(_id=_id, topic=topic, cb=cb)


def manual(topic: str, buf_size: int = 10, overwrite: bool = False) -> tuple:
    """
    Subscribe to a topic with a RingBuffer for manual polling — no callback.

    :param topic:     MQTT-style pattern.
    :param buf_size:  Ring buffer capacity (items, not bytes).
    :param overwrite: If True, oldest message is silently dropped when full.
    :return:          (sub_id: int, buf: RingBuffer)

    Usage::

        sub_id, buf = manual('sensors/#', buf_size=20)

        # later, in your polling loop:
        while not buf.is_empty():
            topic, msg = buf.get()
            process(topic, msg)

        # to unsubscribe:
        off(_id=sub_id)
    """
    return _bus.subscribe(topic, cb=None, buf_size=buf_size, overwrite=overwrite)

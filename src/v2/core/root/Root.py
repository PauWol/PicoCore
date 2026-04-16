from uasyncio import sleep as async_sleep, create_task
from time import ticks_ms, ticks_diff, ticks_add
from machine import lightsleep
import uasyncio
import sys

from core.queue import RingBuffer
from core.config import get_config
from core.constants import (
    POWER_MONITOR_ENABLED,
    SLEEP_INTERVAL,
    EVENT_ROOT_LOOP_BOOT_BEFORE,
    EVENT_ROOT_LOOP_BOOT_AFTER,
    MESH_ENABLED,
)
from core.logging import logger
from .bus import emit
from core.util import boot_flag_task, timed_function
from core.comms.mesh import mesh


"""
SYSTEM   = 0
CORE     = 1
HIGH     = 2
NORMAL   = 3
LOW      = 4
IDLE     = 5
"""


class Task:
    """
    Represents a scheduled task within the root scheduler.

    A task can be:
    - interval-based (runs periodically)
    - one-time (runs once after optional delay)
    - boot task (runs during boot phase only)

    Supports both synchronous and asynchronous callbacks.
    """

    __slots__ = (
        "name",
        "interval",
        "last_run",
        "next_run",
        "callback",
        "async_task",
        "enabled",
        "priority",
        "boot",
        "onetime",
        "parallel",
    )

    def __repr__(self):
        return f"Task(name={self.name}, interval={self.interval}, last_run={self.last_run},next_run={self.next_run}, callback={self.callback}, async_task={self.async_task}, enabled={self.enabled}, priority={self.priority}, boot={self.boot}, parallel={self.parallel})"

    def __init__(
        self,
        name: str,
        callback,
        interval: str | int | None = None,
        async_task: bool = True,
        enabled: bool = True,
        priority: int = 3,
        boot: bool = False,
        onetime: bool = False,
        parallel: bool = False,
    ):
        """
        Initialize a Task.

        :param name: Unique name of the task
        :param callback: Function or coroutine to execute
        :param interval: Execution interval (int ms or str like "1ms", "1s", "5min", "1h"), ignored for boot tasks
        :param async_task: Whether the callback is async (coroutine)
        :param enabled: Whether the task is active
        :param priority: Task priority (lower = higher priority)
        :param boot: If True, runs only during boot phase
        :param onetime: If True, runs only once (optionally delayed by interval)
        :param parallel: If True, runs via create_task (non-blocking)
        """
        self.name = name
        self.callback = callback
        self.async_task = async_task
        self.enabled = enabled
        self.priority = priority
        self.boot = boot
        self.parallel = parallel
        self.onetime = onetime
        self.interval = 0
        self.last_run = 0
        self.next_run = 0
        # TODO: Maybe add self.running param for parallel tasks to prevent multi spawned tasks.
        if boot and interval:
            logger().warn(
                f"Interval {interval} for boot task {name} is ignored: {self.__repr__()} ;Consider Removing!"
            )
            self.interval = 0
        if onetime and boot:
            logger().warn(
                f"Argument 'onetime' is unnecessary for boot task {name}: {self.__repr__()} ;Consider Removing!"
            )
            self.onetime = 0
            return

        if onetime:
            if interval:
                self.interval = self._parse_interval(interval)
                self.next_run = ticks_add(ticks_ms(), self.interval)
            else:
                self.interval = 0
                self.next_run = ticks_ms()

            return

        if interval:
            self.interval = self._parse_interval(interval)
            self.next_run = self.last_run + self.interval

    @staticmethod
    def _parse_interval(interval: str | int) -> int:
        """
        Parse interval string or integer to integer.
        Input can be an integer or a string with "ms", "s", "min" or "h" suffix.
        :param interval: The execution interval as integer or string ("1ms", "1s", "1min", "1h")
        :return: The execution interval in ms
        """
        if isinstance(interval, int):
            return interval

        interval = interval.lower().strip()

        if isinstance(interval, str):
            if interval.endswith("ms"):
                return int(interval[:-2])
            if interval.endswith("s"):
                return int(interval[:-1]) * 1000
            if interval.endswith("min"):
                return int(interval[:-3]) * 1000 * 60
            if interval.endswith("h"):
                return int(interval[:-1]) * 1000 * 60 * 60

        raise ValueError(
            f"Invalid interval format {interval}, should be int (ms) or str with 'ms' , 's' or 'h' suffix"
        )

    def should_run(self, now: int) -> bool:
        """
        Determine if the task should execute at the current time.

        :param now: Current tick time
        :return: True if task should run
        """
        if not self.enabled:
            return False

        # onetime tasks run once when next_run reached
        if self.onetime:
            return ticks_diff(now, self.next_run) >= 0

        if self.interval == 0:
            return False

        return ticks_diff(now, self.next_run) >= 0

    def run(self, now: int):
        """
        Execute a synchronous task.

        Updates scheduling timestamps and disables one-time/boot tasks after execution.

        :param now: Current tick time
        """
        if not self.enabled:
            return

        self.last_run = now
        self.next_run = ticks_add(now, self.interval)
        self.callback()

        if self.boot or self.onetime:
            self.enabled = False

    async def run_async(self, now: int):
        """
        Execute an asynchronous task.

        Updates scheduling timestamps and disables one-time/boot tasks after execution.

        :param now: Current tick time
        """
        if not self.enabled:
            return

        self.last_run = now
        self.next_run = ticks_add(now, self.interval)
        await self.callback()

        if self.boot or self.onetime:
            self.enabled = False


class Root:
    def __init__(self):
        self.conf = get_config()
        self.running = False
        # Interval for async sleep in main loop
        self.sleep_interval = self.conf.get(SLEEP_INTERVAL) or 0.1
        self.power_monitor = self.conf.get(POWER_MONITOR_ENABLED) or False
        self.mesh = (
            bool(self.conf.get(MESH_ENABLED))
            and sys.platform.startswith("esp32")
            or False
        )
        self._mesh = None
        self.dynamic_sleep = False

        # TODO: Maybe make them pre-allocated with fixed max task length / add option for such optimization
        self._boot_tasks = []
        self._tasks = []
        self._pending_tasks = []

        # Is initialized if dynamic sleep is enabled and in loop start first
        self._time_proposal_buffer: RingBuffer | None = None

        # time for actual light- or later deepsleep
        self._min_sleep_time = 100  # ms

        logger().debug("Root initialized")
        self._init_system_tasks()

    def __repr__(self):
        """
        Return a string representation of the root scheduler.
        :return: String representation of the root scheduler
        """
        return f"Root(props={self.__dict__})"

    def _init_system_tasks(self):

        # boot flag task
        self.add(
            Task(
                "boot_flag_task",
                boot_flag_task,
                boot=True,
                priority=0,
                enabled=True,
                parallel=True,
            )
        )

        if self.mesh:
            self._mesh = mesh()
            # mesh task: receive_task
            self.add(
                Task(
                    "mesh_run_task",
                    callback=self._mesh.run,
                    async_task=True,
                    priority=0,
                    enabled=True,
                    parallel=True,
                    boot=True,
                )
            )

        self.optimize()

    def add(self, _task: Task):
        """
        Add a task to the root scheduler.
        :param _task:
        :return:
        """
        if self.running:
            self._pending_tasks.append(_task)
            return

        if _task.boot:
            self._boot_tasks.append(_task)
        else:
            self._tasks.append(_task)

        logger().debug(f"Task {_task.name} added to root scheduler")

    @timed_function
    def optimize(self):
        """
        Optimize the root scheduler.
        :return:
        """
        # sort ONLY if needed
        self._tasks.sort(key=lambda x: x.priority)

        if not self.power_monitor:
            return

        t = None

        for _task in self._tasks:
            if _task.interval > 0 and (t is None or _task.interval < t):
                t = _task.interval

        if t is None:
            self.dynamic_sleep = False
            return

        self._min_sleep_time = max(t, self._min_sleep_time)

        aligned = True
        for _task in self._tasks:
            if _task.interval > 0 and _task.interval % t != 0:
                aligned = False
                break

        self.dynamic_sleep = aligned

        logger().debug("Root scheduler optimized")

    def remove(self, _task: Task | str):
        """
        Remove a task from the root scheduler.
        :param _task: Task object or task name
        :return:
        """
        # TODO: Make remove safe for dynamic tasks / disable them
        if isinstance(_task, str):
            _task = next((t for t in self._tasks if t.name == _task), None)
            if _task is None:
                _task = next((t for t in self._boot_tasks if t.name == _task), None)
                if _task is None:
                    logger().warn(f"Task {_task} not found")
                    return

        if _task.boot:
            self._boot_tasks.remove(_task)
        else:
            self._tasks.remove(_task)

        logger().debug(f"Task {_task.name} removed from root scheduler")

    async def sleep(self):
        """
        This method puts the microcontroller to sleep according to the state of the system.
        :return:
        """

        # If mesh expects traffic, do NOT deep/light sleep
        if self.mesh and self._mesh.rx_expected():
            # short cooperative sleep only
            await async_sleep(self.sleep_interval)
            return

        if self.power_monitor:
            lightsleep(self._min_sleep_time)

            if self.dynamic_sleep:
                if len(self._time_proposal_buffer):
                    self._min_sleep_time = min(self._time_proposal_buffer)
                self._time_proposal_buffer.clear()

            # TODO: Add deepsleep support with state saving
        else:
            await async_sleep(self.sleep_interval)

    @staticmethod
    async def _wrap_sync(_task: Task, now):
        _task.run(now)
        await async_sleep(0)

    @timed_function
    async def boot(self):
        """
        This method is called as representative of boot for root and thus run all tasks marked as boot tasks.
        :return: None
        """
        emit(EVENT_ROOT_LOOP_BOOT_BEFORE, "")
        now = ticks_ms()
        for _task in self._boot_tasks:
            # create background async tasks for parallel ones
            if _task.parallel:
                if _task.async_task:
                    create_task(_task.run_async(now))
                else:
                    create_task(self._wrap_sync(_task, now))
            elif _task.async_task:
                # synchronous await for async tasks that should run before boot continues
                await _task.run_async(now)
            else:
                _task.run(now)

        del self._boot_tasks[:]

        emit(EVENT_ROOT_LOOP_BOOT_AFTER, "")
        logger().debug("Root boot completed")

    async def loop(self):
        """
        The root main execution loop running all tasks (excluded boot marked ones)
        :return:
        """

        # Pre-bind functions to save lookup times
        sleep_ = self.sleep
        ticks_ms_ = ticks_ms
        ticks_diff_ = ticks_diff
        create_task_ = create_task
        optimize_ = self.optimize
        wrap_sync_ = self._wrap_sync
        pending_tasks_ = self._pending_tasks
        # buffer_put = self._time_proposal_buffer.put
        tasks = self._tasks

        self.running = True

        if self.dynamic_sleep:
            logger().warn("Dynamic-sleep capabilities doesn't work in this version.")
            # TODO: Add dynamic sleep support with updated dynamic tasks scheduling while runtime
            self._time_proposal_buffer = RingBuffer(len(self._tasks), True)

        while self.running:
            now = ticks_ms_()

            if pending_tasks_:
                tasks.extend(pending_tasks_)
                pending_tasks_.clear()
                optimize_()

            for _task in tasks:
                if _task.should_run(now):
                    if _task.parallel:
                        if _task.async_task:
                            create_task_(_task.run_async(now))
                        else:
                            create_task_(wrap_sync_(_task, now))
                    elif _task.async_task:
                        await _task.run_async(now)
                    else:
                        _task.run(now)

                if self.dynamic_sleep:
                    t = ticks_diff_(_task.next_run, now)
                    t = max(t, 0)
                    self._time_proposal_buffer.put(t)  # buffer_put(t)
            await sleep_()

    def run(self):
        """
        Start the whole root: boot then main loop.
        """
        try:

            async def _runner():
                await self.boot()
                await self.loop()

            uasyncio.run(_runner())
        except KeyboardInterrupt:
            print("Application stopped manually.")
        # except Exception as e: TODO: enable this
        # logger().fatal( f"Unhandled exception in Root.run: {e}")


_root: Root | None = None


@timed_function
def root() -> Root:
    """
    This returns the root instance of PicoCore Root.
    :return:
    """
    global _root
    if _root is None:
        _root = Root()
    return _root


def task(
    interval: str | int | None,
    async_task: bool = True,
    enabled: bool = True,
    priority: int = 3,
    boot: bool = False,
    onetime: bool = False,
    parallel: bool = False,
):
    """
    Decorator to register a function as a task in the root scheduler.

    The decorated function will be wrapped into a Task object and automatically
    added to the scheduler during definition time.

    :param interval: Execution interval as int (ms) or string ("1ms", "1s", "1min", "1h").
                     If None, the task is not interval-based.
                     Ignored for boot tasks. Used as delay for onetime tasks.
    :param async_task: Whether the function is asynchronous (defined with 'async def').
                       Must be True for coroutine functions.
    :param enabled: Whether the task is active. Disabled tasks will not be executed.
    :param priority: Execution priority (lower value = higher priority).
                     Example: 0 = system, 3 = normal, 5 = idle.
    :param boot: If True, the task runs once during the boot phase before the main loop starts.
    :param onetime: If True, the task runs only once.
                    If interval is provided, it runs once after the delay.
                    If no interval is provided, it runs as soon as possible.
    :param parallel: If True, the task is executed using create_task (non-blocking).
                     Allows concurrent execution but increases resource usage.
                     Recommended for async tasks only.
    :return: The original function, unchanged.
    """

    def deco(fn):
        root().add(
            Task(
                fn.__name__,
                fn,
                interval,
                async_task,
                enabled,
                priority,
                boot,
                onetime,
                parallel,
            )
        )
        return fn

    return deco


def add_task(
    fn,
    interval: str | int | None,
    async_task: bool = True,
    enabled: bool = True,
    priority: int = 3,
    boot: bool = False,
    onetime: bool = False,
    parallel: bool = False,
):
    """
    Register a function as a task in the root scheduler at runtime.

    Unlike the @task decorator, this function allows dynamic task creation
    and insertion while the scheduler is already running.

    :param fn: The function or coroutine to execute.
    :param interval: Execution interval as int (ms) or string ("1ms", "1s", "1min", "1h").
                     If None, the task is not interval-based.
                     Ignored for boot tasks. Used as delay for onetime tasks.
    :param async_task: Whether the function is asynchronous (defined with 'async def').
                       Must be True for coroutine functions.
    :param enabled: Whether the task is active. Disabled tasks will not be executed.
    :param priority: Execution priority (lower value = higher priority).
                     Example: 0 = system, 3 = normal, 5 = idle.
    :param boot: If True, the task runs once during the boot phase.
                 If the scheduler is already running, this has no effect.
    :param onetime: If True, the task runs only once.
                    If interval is provided, it runs once after the delay.
                    Otherwise, it runs as soon as possible.
    :param parallel: If True, the task is executed using create_task (non-blocking).
                     Allows concurrent execution but increases resource usage.
                     Recommended for async tasks only.
    :return: None
    """
    root().add(
        Task(
            fn.__name__,
            fn,
            interval,
            async_task,
            enabled,
            priority,
            boot,
            onetime,
            parallel,
        )
    )


def start():
    """
    This starts the root scheduler.After this no code is executed,hence it blocks the main thread.Needs to be put at the very end of the main.py file to use benefits of PicoCore.
    :return:
    """
    root().run()


def stop():
    """
    This stops the root scheduler.
    :return:
    """
    root().running = False

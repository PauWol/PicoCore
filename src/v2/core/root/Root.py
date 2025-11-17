from uasyncio import sleep as async_sleep, create_task
from time import ticks_ms,ticks_diff
from machine import lightsleep , deepsleep,Pin
from ..queue import RingBuffer
from ..config import get_config
from ..constants import POWER_MONITOR_ENABLED,SLEEP_INTERVAL, EVENT_ROOT_LOOP_BOOT, EVENT_ROOT_LOOP_BOOT_BEFORE, EVENT_ROOT_LOOP_BOOT_AFTER
from ..logging import logger
from .Bus import emit , on
from ..io import Led
from ..util import boot_flag_task
import uasyncio

"""
SYSTEM   = 0
CORE     = 1
HIGH     = 2
NORMAL   = 3
LOW      = 4
IDLE     = 5
"""

class Task:
    __slots__ = ('name', 'interval', 'last_run','next_run', 'callback', 'async_task', 'enabled', 'priority', 'boot', 'parallel')

    def __repr__(self):
        return f"Task(name={self.name}, interval={self.interval}, last_run={self.last_run},next_run={self.next_run}, callback={self.callback}, async_task={self.async_task}, enabled={self.enabled}, priority={self.priority}, boot={self.boot}, parallel={self.parallel})"

    def __init__(self,name: str, callback, interval: str|int|None = None ,async_task:bool = True, enabled: bool = True, priority: int = 3,boot:bool = False,parallel:bool = False):
        self.name = name
        self.callback = callback
        self.async_task = async_task
        self.enabled = enabled
        self.priority = priority
        self.boot = boot
        self.parallel = parallel
        self.interval = 0
        self.last_run = 0
        self.next_run = self.last_run + self.interval
        if interval:
            self.interval = self._parse_interval(interval)
            self.last_run = 0
            self.next_run = self.last_run + self.interval
        if boot and interval:
            logger().warn(f"Interval {interval} for boot task {name} is ignored: {self.__repr__()}")


    @staticmethod
    def _parse_interval(interval: str|int) -> int:
        """
        Parse interval string or integer to integer.
        Input can be an integer or a string with "ms" , "s" or "h" suffix.
        :param interval: The execution interval as integer or string ("1ms", "1s", "1h")
        :return: The execution interval in ms
        """
        if isinstance(interval, int):
            return interval

        interval = interval.lower().strip()

        if isinstance(interval, str):
            if interval.endswith("ms"):
                return int(interval[:-2])
            elif interval.endswith("s"):
                return int(interval[:-1]) * 1000
            elif interval.endswith("min"):
                return int(interval[:-3]) * 1000 * 60
            elif interval.endswith("h"):
                return int(interval[:-1]) * 1000 * 60 * 60
            else:
                raise ValueError("Invalid interval format")
        raise ValueError(f"Invalid interval format {interval}, should be int (ms) or str with 'ms' , 's' or 'h' suffix")

    def should_run(self,now:int) -> bool:
        return self.enabled and (ticks_diff(now , self.last_run)) >= self.interval

    def run(self,now:int):
        self.last_run = now
        self.next_run = self.last_run + self.interval
        self.callback()

        if self.boot:
            self.enabled = False

    async def run_async(self,now:int):
        self.last_run = now
        self.next_run = self.last_run + self.interval
        await self.callback()

        if self.boot:
            self.enabled = False

class Root:
    def __init__(self):
        self.conf = get_config()
        self.running = True
        # Interval for async sleep in main loop
        self.sleep_interval = self.conf.get(SLEEP_INTERVAL) or 0.1
        self.power_monitor = self.conf.get(POWER_MONITOR_ENABLED) or False
        self.dynamic_sleep = False

        self._boot_tasks = []
        self._tasks = []

        # Is initialized if dynamic sleep is enabled and in loop start first
        self._time_proposal_buffer: RingBuffer| None = None

        # time for actual light- or later deepsleep
        self._min_sleep_time = 100 # ms
        self._init_system_tasks()


    def _init_system_tasks(self):

        # boot flag task
        self.add(Task("boot_flag_task",boot_flag_task,boot=True,priority=0,enabled=True,parallel=True))

    def add(self, _task:Task):
        """
        Add a task to the root scheduler.
        :param _task:
        :return:
        """
        if _task.boot:
            self._boot_tasks.append(_task)
        else:
            self._tasks.append(_task)

        self.optimize()

        logger().debug(f"Task {_task.name} added to root scheduler")

    def optimize(self):
        """
        Optimize the root scheduler.
        :return:
        """
        self._boot_tasks.sort(key=lambda x: x.priority)
        self._tasks.sort(key=lambda x: x.priority)

        if self.power_monitor and self._tasks:
            # Set sleep interval to the minimum interval of all tasks must be >= 100 ms.
            t =  min([t.interval for t in self._tasks])
            self._min_sleep_time = t if t > self._min_sleep_time else self._min_sleep_time

            if all(_task.interval % t == 0 for _task in self._tasks):
                self.dynamic_sleep = True

                #TODO: Maybe add else = false

        logger().debug("Root scheduler optimized")

    def remove(self, _task: Task | str):
        """
        Remove a task from the root scheduler.
        :param _task: Task object or task name
        :return:
        """
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
        This method puts the microcontroller to sleep.
        :return: None
        """
        led = Led("LED", Pin.OUT)
        if self.power_monitor and True==False: #TODO: Remove this line,for testing only
            lightsleep(self._min_sleep_time)
        # TODO: Add deepsleep support with state saving
            if self.dynamic_sleep:
                self._min_sleep_time = min(self._time_proposal_buffer)
                self._time_proposal_buffer.clear()
        else:
            await async_sleep(self.sleep_interval)


    async def boot(self):
        """
        This method is called as representative of boot for root and thus run all tasks marked as boot tasks.
        :return: None
        """
        emit(EVENT_ROOT_LOOP_BOOT_BEFORE,"")
        now = ticks_ms()
        for _task in self._boot_tasks:
            if _task.async_task:
                await _task.run_async(now)
            elif _task.parallel:
                create_task(_task.run_async(now))
            else:
                _task.run(now)

        del self._boot_tasks[:]

        emit(EVENT_ROOT_LOOP_BOOT_AFTER,"")
        logger().debug(f"Root boot completed")



    async def loop(self):
        """
        The root main execution loop running all tasks (excluded boot marked ones)
        :return:
        """
        if self.dynamic_sleep:
            self._time_proposal_buffer = RingBuffer(len(self._tasks),True)

        while self.running:
            now = ticks_ms()
            for _task in self._tasks:
                if _task.should_run(now):
                    if _task.async_task:
                        await _task.run_async(now)
                    elif _task.parallel:
                        create_task(_task.run_async(now))
                    else:
                        _task.run(now)

                if self.dynamic_sleep:
                    self._time_proposal_buffer.put(ticks_diff(_task.next_run,now)) #TODO: Review this line
            await self.sleep()

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
        except Exception as e:
            logger().fatal( f"Unhandled exception in Root.run: {e}")



_root: Root|None = None

def root() -> Root:
    """
    This returns the root instance of PicoCore Root.
    :return:
    """
    global _root
    if _root is None:
        _root = Root()
    return _root



def task(interval: str|int, async_task: bool = True, enabled: bool = True, priority: int = 3,boot: bool = False,parallel: bool = False):
    """
    This decorator is used to add a task to the root scheduler.
    :param interval:  The execution interval as integer or string ("1ms", "1s", "1h").
    :param async_task:  Weather your task is async or not (needs to be True if your task is async, so if 'async def your_task()').
    :param enabled: If the task is enabled or not.Needs to be True to run.
    :param priority:  Execution priority of the task. Lower values mean higher priority (0 = system; 3 = Normal ; 5 = Idle).
    :param boot: Weather your task should run at root loop 'boot' time (before start of root exe loop)
    :param parallel: Runs your task with create_task (only when async) requires more resources but allows main loop to continue while task is running
    :return:
    """
    def deco(fn):
        root().add(Task(fn.__name__,fn,interval, async_task, enabled, priority,boot,parallel))
        return fn
    return deco


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
    root().running  = False
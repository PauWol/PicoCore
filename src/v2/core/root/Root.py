from uasyncio import sleep as async_sleep, create_task
from time import ticks_ms,ticks_diff
from ..config import get_config
from ..constants import POWER_MONITOR_ENABLED,SLEEP_INTERVAL, EVENT_ROOT_LOOP_BOOT, EVENT_ROOT_LOOP_BOOT_BEFORE, EVENT_ROOT_LOOP_BOOT_AFTER
from ..logging import logger
from .Bus import emit , on
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
    __slots__ = ('name', 'interval', 'last_run', 'callback', 'async_task', 'enabled', 'priority', 'boot', 'parallel')

    def __repr__(self):
        return f"Task(name={self.name}, interval={self.interval}, last_run={self.last_run}, callback={self.callback}, async_task={self.async_task}, enabled={self.enabled}, priority={self.priority}, boot={self.boot}, parallel={self.parallel})"

    def __init__(self,name: str, interval: str|int, callback,async_task:bool = True, enabled: bool = True, priority: int = 3,boot:bool = False,parallel:bool = False):
        self.name = name
        self.interval = self._parse_interval(interval)
        self.last_run = 0
        self.callback = callback
        self.async_task = async_task
        self.enabled = enabled
        self.priority = priority
        self.boot = boot
        self.parallel = parallel

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
        elif isinstance(interval, str):
            if interval.endswith("ms"):
                return int(interval[:-2])
            elif interval.endswith("s"):
                return int(interval[:-1]) * 1000
            elif interval.endswith("h"):
                return int(interval[:-1]) * 1000 * 60 * 60
            else:
                raise ValueError("Invalid interval format")
        raise ValueError(f"Invalid interval format {interval}, should be int (ms) or str with 'ms' , 's' or 'h' suffix")

    def should_run(self,now:int) -> bool:
        return self.enabled and (ticks_diff(now , self.last_run)) >= self.interval

    def run(self,now:int):
        self.last_run = now
        self.callback()

        if self.boot:
            self.enabled = False

    async def run_async(self,now:int):
        self.last_run = now
        await self.callback()

        if self.boot:
            self.enabled = False

class Root:
    def __init__(self):
        self.conf = get_config()
        self.running = True
        self.sleep_interval = self.conf.get(SLEEP_INTERVAL) or 0.1

        self._boot_tasks = []
        self._tasks = []

        self._init_system_tasks()

    def _init_system_tasks(self):
        pass

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

        logger().debug("Root",f"Task {_task.name} added to root scheduler", "add")

    def optimize(self):
        """
        Optimize the root scheduler.
        :return:
        """
        self._boot_tasks.sort(key=lambda x: x.priority)
        self._tasks.sort(key=lambda x: x.priority)
        logger().debug("Root",f"Root scheduler optimized","optimize")

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
                    logger().warn("Root",f"Task {_task} not found", "remove")
                    return

        if _task.boot:
            self._boot_tasks.remove(_task)
        else:
            self._tasks.remove(_task)

        logger().debug("Root",f"Task {_task.name} removed from root scheduler", "remove")

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
        logger().debug("Root",f"Root boot completed","boot")


    async def loop(self):
        """
        The root main execution loop running all tasks (excluded boot marked ones)
        :return:
        """

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
            await async_sleep(self.sleep_interval)

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
            logger().fatal("Root", f"Unhandled exception in Root.run: {e}", "run")



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
        root().add(Task(fn.__name__, interval, fn, async_task, enabled, priority,boot,parallel))
        return fn
    return deco


def start():
    """
    This starts the root scheduler.After this no code is executed,hence it blocks the main thread.Needs to be put at the very end of the main.py file to use benefits of PicoCore.
    :return:
    """
    root().run()
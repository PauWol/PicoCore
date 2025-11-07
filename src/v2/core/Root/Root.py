from uasyncio import sleep as async_sleep
from ..config import get_config
from ..constants import POWER_MONITOR_ENABLED,SLEEP_INTERVAL
from .Power import Power
import uasyncio


class Root:
    def __init__(self):
        self.conf = get_config()
        self.running = True

        self._services = []

        self._init_sub_services()
        print("root init")

    def _is_awaitable(self,function) -> bool:
        return hasattr(function, "__await__") or callable(getattr(function, "send", None))

    def _init_sub_services(self):

        if self.conf.get(POWER_MONITOR_ENABLED):
            self._services.append(Power())
            print("Power monitor enabled")

    async def exe_service_func(self, func_name):
        for service in self._services:
            if service is None:
                continue

            # print("tick ->", service.__class__.__name__)

            try:
                res = service.__getattribute__(func_name)()  # may be: None, sync result, coroutine, or generator-based coroutine
            except Exception as e:
                print("service.tick() raised immediately:", e)
                continue

            # robust awaitable detection that doesn't use `types`:
            is_awaitable = self._is_awaitable(res)

            if is_awaitable:
                try:
                    await res
                except Exception as e:
                    print("  service", service.__class__.__name__, "raised in tick():", e)
            else:
                # sync function already executed or returned generator-like object that wasn't awaitable
                print("  sync tick done for", service.__class__.__name__)

    async def tick(self):
        """
        Run one tick for each service. Works on MicroPython (generator-style coroutines)
        and CPython (coroutine objects) without importing `types`.
        """
        await self.exe_service_func("tick")

    async def check(self):
        await self.exe_service_func("check")

    def data(self):
        # unchanged but use property access (not call)
        x = []
        for service in self._services:
            if service is None:
                continue
            x.append(service.data)
        return x

    async def loop(self):
        """Main repeating loop — never returns (until cancelled)."""
        sleep_ms = self.conf.get(SLEEP_INTERVAL)
        # convert ms->seconds for uasyncio.sleep
        sleep_s = float(sleep_ms) / 1000.0
        while self.running:
            await self.tick()
            data = self.data()
            # do something with data if needed, or call evaluate()
            # self.evaluate()
            await async_sleep(sleep_s)

    def run(self):
        try:
            uasyncio.run(self.check())
            uasyncio.run(self.loop())
        except KeyboardInterrupt:
            print("Application stopped manually.")







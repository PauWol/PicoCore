from machine import Pin
import uasyncio as asyncio

class Led:
    def __init__(self,pin:int,*args):
        self.pin = Pin(pin,*args)

    def on(self):
        self.pin.value(1)

    def off(self):
        self.pin.value(0)

    def toggle(self):
        self.pin.value(not self.pin.value())

    def state(self):
        return self.pin.value()

    async def async_on(self):
        self.pin.value(1)

    async def async_off(self):
        self.pin.value(0)

    async def async_toggle(self):
        self.pin.value(not self.pin.value())

    async def async_blink(self,n:int, delay: float):
        """
        Turn on and of the LED for n times with a delay of delay seconds.
        :param n:
        :param delay:
        :return:
        """
        for _ in range(n):
            await self.async_toggle()
            await asyncio.sleep(delay)
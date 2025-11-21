"""
PicoCore V2 LED Class

This class provides a class for controlling an LED with asyncio support.
"""

from machine import Pin
import uasyncio as asyncio

class Led:
    """
    LED interface class
    """
    def __init__(self,pin:int,*args):
        """
        Initialize the LED.
        :param pin: Number of the desired pin.
        :param args: Arguments for the Pin class (e.g. Pin.OUT).
        """
        self.pin = Pin(pin,*args)

    def on(self):
        """
        Turn on the LED.
        :return:
        """
        self.pin.value(1)

    def off(self):
        """
        Turn off the LED.
        :return:
        """
        self.pin.value(0)

    def toggle(self):
        """
        Toggle the LED.
        :return:
        """
        self.pin.value(not self.pin.value())

    def state(self):
        """
        Return the state of the LED.
        :return:
        """
        return self.pin.value()

    async def async_on(self):
        """
        Turn on the LED.
        :return:
        """
        self.pin.value(1)

    async def async_off(self):
        """
        Turn off the LED.
        :return:
        """
        self.pin.value(0)

    async def async_toggle(self):
        """
        Toggle the LED.
        :return:
        """
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

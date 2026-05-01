"""
PicoCore V2 – NeoPixel LED Driver
==================================
Drop-in replacement for io.Led on boards whose only user LED is a WS2812B
NeoPixel (e.g. ESP32-S3-DevKitC-1, pin 48).

Public surface intentionally mirrors io.Led so all call-sites in __init__.py
remain untouched, but a richer animated boot sequence is also available.

Boot state machine
------------------
  "config"    cyan   breathe   – loading config.toml
  "log"       blue   breathe   – initializing logger
  "root"      indigo breathe   – spinning up root scheduler
  "safe"      yellow fast-pulse – double-boot / safe-mode check
  "done"      green  sweep out  – healthy boot complete
  "safe_mode" red    solid      – safe mode active

Usage (inside __init__.py)
--------------------------
    led = led_init()                            # returns NeoLed or io.Led

    # For NeoLed: start the animator immediately (parallel, non-blocking):
    if hasattr(led, 'start_boot_animation'):
        led.start_boot_animation()

    led.set_boot_state("log")                   # advance as each phase finishes
    ...
    led.finish_boot(safe_mode=False)            # end animation
"""

import machine
import neopixel
import asyncio

# ── colour palette ────────────────────────────────────────────────────────────

_OFF = (0, 0, 0)
_RED = (255, 0, 0)
_GREEN = (0, 255, 0)
_BLUE = (0, 0, 255)
_CYAN = (0, 255, 255)
_YELLOW = (255, 180, 0)
_INDIGO = (60, 0, 180)
_WHITE = (255, 255, 255)

# Global brightness scale – keeps the pixel from being blinding on a desk.
# 0.06 ≈ 6 % of full power; plenty visible in normal lighting.
_GLOBAL_BRIGHTNESS: float = 0.06


def _scale(color: tuple, factor: float) -> tuple:
    """Scale an RGB tuple by factor (0.0–1.0)."""
    return (
        int(color[0] * factor),
        int(color[1] * factor),
        int(color[2] * factor),
    )


class NeoLed:
    """
    Single-pixel WS2812B driver with the same interface as io.Led.

    Parameters
    ----------
    pin : int
        GPIO pin the NeoPixel data line is connected to.
    num_pixels : int
        Number of pixels in the strip/ring (almost always 1 for DevKit boards).
    brightness : float
        Global brightness scale 0.0–1.0 (default 0.06 – dim but visible).
    """

    def __init__(
        self,
        pin: int,
        num_pixels: int = 1,
        brightness: float = _GLOBAL_BRIGHTNESS,
    ):
        self._np = neopixel.NeoPixel(machine.Pin(pin), num_pixels)
        self._color = _GREEN  # default "on" colour
        self._brightness = brightness
        self._boot_state = "config"
        self._boot_done = False

    def _write(self, color: tuple):
        self._np[0] = color
        self._np.write()

    def _dim(self, color: tuple, extra: float = 1.0) -> tuple:
        return _scale(color, self._brightness * extra)

    def set_color(self, color: tuple):
        """
        Change the color used by on() and blink().

        :param color:
        """
        self._color = color

    def on(self):
        """Turn the pixel on with the current color."""
        self._write(self._dim(self._color))

    def off(self):
        """Turn the pixel off."""
        self._write(_OFF)

    def blink(self, times: int = 3, delay: float = 0.2, color: tuple = None):
        """
        Blocking blink – avoid calling from an async context.

        :param times:
        :param delay:
        :param color:
        """
        import time

        c = self._dim(color or self._color)
        for _ in range(times):
            self._write(c)
            time.sleep(delay)
            self._write(_OFF)
            time.sleep(delay)

    async def async_blink(
        self,
        times: int = 6,
        delay: float = 0.2,
        color: tuple = None,
    ):
        """
        Non-blocking blink

        :param times:
        :param delay:
        :param color:
        """
        c = self._dim(color or self._color)
        for _ in range(times):
            self._write(c)
            await asyncio.sleep(delay)
            self._write(_OFF)
            await asyncio.sleep(delay)

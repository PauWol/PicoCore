"""
PicoCore V2 Util Module

This module provides utility functions for file operations, system information,
and other common tasks.
"""
import time
import os
import sys
import machine
import uasyncio as asyncio
from .constants import BOOT_FLAG, BOOT_WINDOW_MS



def _file_exists(name):
    try:
        return name in os.listdir()
    except FileNotFoundError:
        # if filesystem not mounted or error -> conservatively assume no file
        try:
            return name in os.listdir("/")   # fallback
        except FileNotFoundError:
            return False

def _create_boot_flag(encoding:str = "utf-8"):
    try:
        with open(BOOT_FLAG, "w",encoding=encoding) as f:
            f.write("1")
    except OSError:
        # silently ignore write errors (rare)
        pass

def _remove_boot_flag():
    try:
        if _file_exists(BOOT_FLAG):
            os.remove(BOOT_FLAG)
    except OSError:
        # ignore errors; not critical
        pass

async def _delayed_clear_boot_flag():
    # Run as uasyncio task; sleeps, then removes flag.
    await asyncio.sleep_ms(BOOT_WINDOW_MS)
    _remove_boot_flag()

async def boot_flag_task():
    """
    This function checks if the boot flag file exists and if it does,
    it runs the _delayed_clear_boot_flag function.
    :return:
    """
    if _file_exists(BOOT_FLAG):
        await _delayed_clear_boot_flag()


def create_file(path:str, encoding:str = "utf-8"):
    """
    This function creates a file at the specified path.
    :param encoding: The encoding to use when writing the file.
    :param path: The path to the file to create.
    :return:
    """
    with open(path, "w",encoding=encoding) as f:
        f.write("")

def uptime(ms: bool = False, formatted: bool = False) -> int | str:
    """
    Get the system uptime since boot.

    This function calculates the time elapsed since the system started by measuring
    the difference between the current tick count and zero. The uptime can be
    returned in different formats based on the provided parameters.

    Args:
        ms (bool, optional): If True, returns uptime in milliseconds.
                            If False, returns uptime in seconds (rounded).
                            Defaults to False.
        formatted (bool, optional): If True, returns a human-readable formatted
                                   string in "Xd HH:MM:SS" format (days, hours,
                                   minutes, seconds). Takes precedence over ms
                                   parameter. Defaults to False.

    Returns:
        int | str: System uptime as:
                  - int: seconds (default) or milliseconds if ms=True
                  - str: formatted string "Xd HH:MM:SS" if formatted=True

    Example:
        >>> uptime()  # Returns seconds as int, e.g., 3661
        >>> uptime(ms=True)  # Returns milliseconds as int, e.g., 3661234
        >>> uptime(formatted=True)  # Returns "0d 01:01:01"

    Note:
        The formatted output shows days, hours (24-hour format), minutes, and seconds.
        Hours, minutes, and seconds are zero-padded to two digits.
    """

    # get uptime in ms
    uptime_ms = time.ticks_diff(time.ticks_ms(), 0)

    if formatted:
        total_ms = uptime_ms
        total_s, _ = divmod(total_ms, 1000)
        m, s = divmod(total_s, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        return f"{d}d {h:02}:{m:02}:{s:02}"

    if ms:
        return uptime_ms

    # return seconds rounded
    return round(uptime_ms / 1000)


def uuid(byte: bool = False) -> bytes | str:
    """
    Get the unique identifier of the microcontroller.

    This function retrieves the unique ID from the microcontroller's hardware.
    The ID can be returned either as raw bytes or as a hexadecimal string.

    Args:
        byte (bool, optional): If True, returns the raw bytes. If False,
                              returns the hexadecimal string representation.
                              Defaults to False.

    Returns:

                    otherwise as a hexadecimal string.

    Example:
        >>> uuid()  # Returns hex string like 'e6614c311b2c5c28'
        >>> uuid(byte=True)  # Returns raw bytes
    """
    if byte:
        return machine.unique_id()

    return machine.unique_id().hex()

def version() -> tuple[str, str]:
    """
    Get the current version of PicoCore.

    :return: The version string in semantic
            versioning format (e.g., ["2.0.0" , "1.26.1"] ).
    :raises ValueError: If the version file could not be read.
    """
    if os.stat("./.version").st_size >= 13:
        with open("./.version", "r",encoding="utf-8") as version_file:
            return version_file.read().strip().split("\n")
    else:
        raise ValueError("Version file could not be read."
                         "Please check if the file exists and is not empty.")



def get_onboard_led() -> int | str:
    """
    Get the onboard LED pin. (Platform dependent)
    :return: The onboard LED pin.
    """
    platform = sys.platform

    # -------------------------
    # Raspberry Pi Pico / Pico W
    # -------------------------
    if platform.startswith("rp2"):              # Pi Pico
        try:
            return "LED"
        except Exception as e:
            raise RuntimeError("Pico LED not available") from e

    # -------------------------
    # ESP32 family
    # -------------------------
    if platform.startswith("esp32"):            # ESP32, ESP32-C3, S2, S3
        candidate_pins = (2, 8, 19, 38)         # common boards

        for pin in candidate_pins:
            try:
                p = machine.Pin(pin, machine.Pin.OUT)
                p.value(1)                      # test LED ON
                p.value(0)                      # OFF
                return pin
            except Exception:
                pass


    # -------------------------
    # Other systems
    # -------------------------
    raise RuntimeError("Unsupported platform: " + platform)

ONBOARD_LED: str | int | None = get_onboard_led()

"""
PicoCore V2 Core Module.

This module is the core of PicoCore V2.
It provides all modules and functions inherent to PicoCore V2.

The following example is just the bare minimum to initiate and start the Root loop.
More information can be found on the GitHub repository and its documentation site:
-> https://github.com/PauWol/PicoCore.git ; https://pauwol.github.io/PicoCore/ .
Usage:
    from core import start,task
    from core.logging import logger

    @task("10s",False,boot=True)
    def test():
        logger().info("Your code works!")
        logger().info("Main loop is running!")

    start()
"""
import time
from machine import Pin
from . import config
from .root import root , start , task , on , bus , emit , manual , off, stop
from . import io
from . import logging
from . import constants
from .util import (version , uuid , uptime , _file_exists , BOOT_FLAG ,
                   _remove_boot_flag , _create_boot_flag,ONBOARD_LED)

__all__ = ['version', 'uuid','root','init','uptime','io','logging',
           'constants','config','task','on','bus','emit','manual',
           'off','start','ONBOARD_LED'
        ]





# call this from boot.py (early) or from Root.boot() before starting scheduler
def check_double_boot_and_maybe_enter_safe_mode():
    """
    Usage:
      - call early during startup.
      - Pass your Root instance so we can stop the scheduler if safe mode triggered.
    Returns True if safe mode was entered, False otherwise.
    """
    # if boot flag exists → double-boot detected
    if _file_exists(BOOT_FLAG):
        # remove flag so future boots are normal
        _remove_boot_flag()
        # Enter safe mode now
        stop()
        return True

    # otherwise create the flag and schedule a deferred removal
    _create_boot_flag()

    # schedule deletion after BOOT_WINDOW_MS inside event loop.
    # We cannot create uasyncio tasks safely from here if event loop not running.
    # So return a small marker that main boot sequence / Root.boot should
    # schedule the deletion task once uasyncio loop is running.

    return False


def init():
    """
    Initialize PicoCore.All boot time configuration is executed here.
    Needs to be called at the very start of the boot.py file to use benefits of PicoCore.
    :return:
    """
    # Get/Initiate config
    config.get_config("config.toml")
    # Initiate logging
    logging.init_logger()
    # Initiate root
    root()
    safe_boot = check_double_boot_and_maybe_enter_safe_mode()

    led = io.Led(ONBOARD_LED, Pin.OUT)

    for _ in range(3):
        led.toggle()
        time.sleep(0.2)
        led.toggle()
        time.sleep(0.2)

    led.off()

    if safe_boot:
        led.on()

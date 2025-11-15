from . import config
from .root import root , start , task , on , bus , emit , manual , off, stop
from . import io
from . import logging
from . import constants
from .util import version , uuid , uptime

__all__ = ['version', 'uuid','root','init','uptime','io','logging','constants','config','task','on','bus','emit','manual','off','start']





# call this from boot.py (early) or from Root.boot() before starting scheduler
def check_double_boot_and_maybe_enter_safe_mode():
    """
    Usage:
      - call early during startup.
      - Pass your Root instance so we can stop the scheduler if safe mode triggered.
    Returns True if safe mode was entered, False otherwise.
    """
    from .util import _file_exists , BOOT_FLAG , remove_boot_flag , create_boot_flag
    # if boot flag exists → double-boot detected
    if _file_exists(BOOT_FLAG):
        # remove flag so future boots are normal
        remove_boot_flag()
        # Enter safe mode now
        stop()
        return True

    # otherwise create the flag and schedule a deferred removal
    create_boot_flag()

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
    conf =config.get_config("config.toml")
    # Initiate logging
    logging.init_logger() # TODO: Parse config args
    # Initiate root
    root()
    sb = check_double_boot_and_maybe_enter_safe_mode()


    # TODO: Use actual internal hardware indicator lib
    import time
    from machine import Pin

    led = io.Led("LED", Pin.OUT)

    for _ in range(3):
        led.toggle()
        time.sleep(0.2)
        led.toggle()
        time.sleep(0.2)

    led.off()

    if sb:
        led.on()



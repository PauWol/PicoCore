import os
import uasyncio as asyncio
from .constants import BOOT_FLAG, BOOT_WINDOW_MS



def _file_exists(name):
    try:
        return name in os.listdir()
    except Exception:
        # if filesystem not mounted or error -> conservatively assume no file
        try:
            return name in os.listdir("/")   # fallback
        except Exception:
            return False

def create_boot_flag():
    try:
        with open(BOOT_FLAG, "w") as f:
            f.write("1")
    except Exception:
        # silently ignore write errors (rare)
        pass

def remove_boot_flag():
    try:
        if _file_exists(BOOT_FLAG):
            os.remove(BOOT_FLAG)
    except Exception:
        # ignore errors; not critical
        pass

async def _delayed_clear_boot_flag():
    # Run as uasyncio task; sleeps, then removes flag.
    await asyncio.sleep_ms(BOOT_WINDOW_MS)
    remove_boot_flag()

async def boot_flag_task():
    if _file_exists(BOOT_FLAG):
        await _delayed_clear_boot_flag()
from machine import ADC, freq , reset , soft_reset
from gc import collect, mem_free, mem_alloc
from os import statvfs
from time import ticks_ms, ticks_us


def BOARD_TEMP():
    """Get the temperature of the device in degrees C."""
    return 27 - (ADC(4).read_u16() * 3.3 / 65535 - 0.706) / 0.001721


def BOARD_RAM_USAGE():
    """
    Get the RAM usage of the device.

    Returns a tuple of three values:
        - usage_percent (float): The percentage of RAM used.
        - used_ram (int): The amount of RAM used in bytes.
        - total_ram (int): The total amount of RAM in bytes.
    """
    collect()
    used_ram = mem_alloc()
    free_ram = mem_free()
    total_ram = used_ram + free_ram
    usage_percent = (used_ram / total_ram) * 100 if total_ram > 0 else 0
    return usage_percent, used_ram, total_ram


def BOARD_FLASH_USAGE():
    """
    Get the flash usage of the device.

    Returns a tuple of three values:
        - usage_percent (float): The percentage of flash used.
        - used_flash (int): The amount of flash used in bytes.
        - total_flash (int): The total amount of flash in bytes.
    """
    stats = statvfs("/")
    total_flash = stats[0] * stats[2]  # Block size * Total blocks
    free_flash = stats[0] * stats[3]  # Block size * Free blocks
    used_flash = total_flash - free_flash
    usage_percent = (used_flash / total_flash) * 100 if total_flash > 0 else 0
    return usage_percent, used_flash, total_flash


def BOARD_CPU_LOAD(duration_ms: int = 100):
    """Get the estimated CPU load of the device in percentage."""
    start_time = ticks_ms()
    busy_time = 0
    end_time = start_time + duration_ms

    while ticks_ms() < end_time:
        busy_start = ticks_us()
        while ticks_us() - busy_start < 10:  # Keep the CPU busy for 10µs
            pass
        busy_time += 10  # Increment busy time

    cpu_load = (busy_time / (duration_ms * 1000)) * 100  # Convert to percentage
    return cpu_load


def BOARD_STATS():
    """Get the stats of the device."""
    return {
        "temp": BOARD_TEMP(),
        "ram_usage": BOARD_RAM_USAGE(),
        "flash_usage": BOARD_FLASH_USAGE(),
        "cpu_load": BOARD_CPU_LOAD()
    }


def setCPUFrequency(mode: str = "normal"):
    """
    Sets the CPU frequency of the Raspberry Pi Pico based on the selected mode.

    :param:
        mode (str): The mode to set the CPU frequency to. Can be "max", "high", "low", or "normal".
    """
    if mode == "max":
        freq(200_000_000)
    elif mode == "high":
        freq(133_000_000)
    elif mode == "low":
        freq(80_000_000)
    else:  # Default to "normal" if mode is unknown
        freq(125_000_000)

def RESET(soft:bool = False):
    """Resets the device."""

    if soft:
        soft_reset()
    else:
        reset()

if __name__ == "__main__":
    #print(BOARD_STATS())
    import time
    setCPUFrequency("low")

    try:
        while True:
           time.sleep(1)
           print("TEMP: ", BOARD_TEMP(), "CPU LOAD: ", BOARD_CPU_LOAD())
    except KeyboardInterrupt:
        setCPUFrequency()
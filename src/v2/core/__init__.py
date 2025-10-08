from . import config
from .root import Root

__all__ = ['version', 'uuid']


def version() -> str:
    """
    Get the current version of PicoCore.
    
    Returns:
        str: The version string in semantic versioning format (e.g., "2.0.0").
    """
    return "2.0.0"


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

    import machine
    if byte:
        return machine.unique_id()

    return machine.unique_id().hex()


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
    import time

    # get uptime in ms
    uptime_ms = time.ticks_diff(time.ticks_ms(), 0)

    if formatted:
        total_ms = uptime_ms
        total_s, remainder_ms = divmod(total_ms, 1000)
        m, s = divmod(total_s, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        return f"{d}d {h:02}:{m:02}:{s:02}"

    if ms:
        return uptime_ms

    # return seconds rounded
    return round(uptime_ms / 1000)


def init():
    """
    Initialize PicoCore.All boot time configuration is executed here.
    :return:
    """
    from config import get_config

    # Read config and initiate root with it TODO: Implement actual init
    get_config("config.toml")





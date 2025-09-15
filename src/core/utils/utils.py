# safe_utils.py  (replace your utils file content with this)

from uos import stat, remove, rename
from machine import RTC
from time import localtime
from struct import pack

def parse_unix_timestamp(ts: int) -> tuple:
    """Takes a raw Unix timestamp and returns a time.struct_time."""
    return localtime(ts)

def sync_rtc(ts: int):
    """Syncs the RTC with the current Unix timestamp to sync the clock."""
    RTC().datetime(parse_unix_timestamp(ts))

def file_exists(path: str) -> bool:
    """Check if a file exists."""
    try:
        stat(path)
        return True
    except OSError:
        return False

def clear_bin_file(path: str) -> None:
    """Clears a binary file (truncate). Use only when you explicitly want to erase it."""
    with open(path, "wb") as f:
        # write zero bytes -> truncates file
        pass

def create_bin_file(path: str) -> None:
    """
    Create the file if it doesn't exist. IMPORTANT: this will NOT truncate an existing file.
    """
    if not file_exists(path):
        # open in append mode and close immediately — creates file but won't overwrite existing file
        with open(path, "ab") as f:
            pass

def get_file_size(path: str) -> int:
    """Returns the size of a file in bytes."""
    try:
        return stat(path)[6]
    except OSError:
        return 0

def append_bytes(path: str, buffer: bytes) -> None:
    """Append bytes to a file (atomic enough for our use)."""
    # 'ab' is append-binary and won't truncate
    with open(path, "ab") as f:
        f.write(buffer)

def format_time(timestamp):
    """Formats a Unix timestamp into a human-readable string."""
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*localtime(timestamp)[:6])

def time_to_bytes(timestamp):
    """Converts a Unix timestamp to a bytes object (4 bytes, big-endian)."""
    return pack(">I", int(timestamp))

def rotate_file(path: str, max_rotations: int = 3) -> None:
    """
    Rotate path -> path.1 -> path.2 ... up to max_rotations. Removes oldest if needed.
    """
    # remove oldest
    oldest = "{}.{}".format(path, max_rotations)
    try:
        if file_exists(oldest):
            remove(oldest)
    except OSError:
        pass

    # shift rotations up
    for i in range(max_rotations - 1, 0, -1):
        src = "{}.{}".format(path, i)
        dst = "{}.{}".format(path, i + 1)
        try:
            if file_exists(src):
                rename(src, dst)
        except OSError:
            pass

    # rotate main to .1
    try:
        if file_exists(path):
            rename(path, "{}.1".format(path))
    except OSError:
        pass

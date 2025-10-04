from core.constants.constants import ERROR_TABLE, LOG_LEVELS, domain_to
from core.logger import get_logger

# Error count since boot
error_count_since_boot = 0

def get_error_count_since_boot():
    """Returns the current error count since boot."""
    return error_count_since_boot

def increment_error_count_since_boot():
    """Increments the error count since boot."""
    global error_count_since_boot
    error_count_since_boot += 1

def decrement_error_count_since_boot():
    """Decrements the error count since boot."""
    global error_count_since_boot
    error_count_since_boot -= 1

def set_error_count_since_boot(value):
    """Sets the error count since boot."""
    global error_count_since_boot
    error_count_since_boot = value

def reset_error_count_since_boot():
    """Resets the error count since boot."""
    global error_count_since_boot
    error_count_since_boot = 0

def raiseError(level: bytes, domain:int , message: str = ""):
    error = PicoOSError(level, domain, message)
    if level >= LOG_LEVELS["CRITICAL"]:
        ErrorCodes.handle(error)
    else:
        get_logger().info(domain_to(domain), message,"error.py:36")



class PicoOSError(Exception):
    """Base class for PicoOS errors."""
    def __init__(self, level:bytes, domain:int, message:str=""):
        self.level = level  # First byte: severity
        self.domain = domain
        self.message = message
        super().__init__(message)

    def __str__(self):
        return f"PicoOSError(level=0x{self.level:02X}, domain=0x{self.domain:02X}): {self.message}"


class ErrorCodes:
    _table = ERROR_TABLE

    @classmethod
    def register(cls,name: str, domain: int, level: int, resolver, auto_resolve=True):
        cls._table[domain][level] = (name, resolver, auto_resolve)

    @classmethod
    def get(cls, level, domain):
        """
        Retrieve error details based on both severity and code.
        """
        if domain in cls._table and level in cls._table[domain]:
            return cls._table[domain][level]  # Return specific level match
        return None

    @classmethod
    def handle(cls, error: PicoOSError):
        entry = cls.get(error.level, error.domain)
        if not entry:
            get_logger().error(error.domain, error.message,"error.py:72")
            increment_error_count_since_boot()  # Increment because it's an unknown error
            return False

        name, resolver, auto_resolve = entry

        log_func = get_logger().error if error.level >= LOG_LEVELS["CRITICAL"] else get_logger().info
        log_func(error.domain, f"{name}: {error.message}","error.py:79")

        if error.level >= LOG_LEVELS["CRITICAL"] and not auto_resolve:
            increment_error_count_since_boot()  # Only increment for unresolved errors

        return resolver() if auto_resolve else False


if "__main__" == __name__:
    from core.constants.constants import LVL_FATAL,UNKNOWN
    try:
        raise PicoOSError(LVL_FATAL,UNKNOWN,"Test")
    except PicoOSError as e:
        ErrorCodes.handle(e)





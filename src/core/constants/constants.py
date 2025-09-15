from micropython import const

# Log framing markers (Start/End of Byte)
LOG_HDR_SOB = const(b"\xA1") # Start Origin Byte
LOG_HDR_EOB = const(b"\xAF") # End Origin Byte

# Data framing markers (Start / Middle / End of Byte)
DATA_HDR_SDB = const(b"\xB1")  # Start Data Byte
DATA_HDR_MDB = const(b"\xB5")  # Middle Data Byte
DATA_HDR_EDB = const(b"\xBF")  # End Data Byte

# Log severity levels
LVL_FATAL    = const(b"\x06")
LVL_CRITICAL = const(b"\x05")
LVL_WARN     = const(b"\x04")
LVL_INFO     = const(b"\x03")
LVL_DEBUG    = const(b"\x02")
LVL_UNKNOWN  = const(b"\x01")
LVL_OFF      = const(b"\x00")

LOG_LEVELS = {
    "FATAL": LVL_FATAL,
    "CRITICAL": LVL_CRITICAL,
    "WARN": LVL_WARN,
    "INFO": LVL_INFO,
    "DEBUG": LVL_DEBUG,
    "UNKNOWN": LVL_UNKNOWN,
    "OFF": LVL_OFF,
}

LOG_LEVELS_REV = {v: k for k, v in LOG_LEVELS.items()}


# Logging Constants

UNKNOWN = "UNKNOWN"
SERVICE_INIT = "SERVICE INIT"
SERVICE_START = "SERVICE START"
SERVICE_STOP = "SERVICE STOP"
SERVICE_RESTART = "SERVICE RESTART"
PARAMETER = "PARAMETER"
BOARD_TEMP = "BOARD TEMP"
SYSTEM = "SYSTEM"
SYSTEM_RESTART = "SYSTEM RESTART"
CPU = "CPU"
RAM = "RAM"
FLASH_MEM = "FLASH MEMORY"
OVERFLOW = "OVERFLOW"

# Logging table with general domain names

LOGGING_TABLE = {
    UNKNOWN : 0,
    SERVICE_INIT : 1,
    SERVICE_START : 2,
    SERVICE_STOP : 3,
    SERVICE_RESTART : 4,
    PARAMETER : 5,
    BOARD_TEMP : 6,
    SYSTEM_RESTART : 7,
    SYSTEM : 8,
    CPU : 9,
    RAM : 10,
    FLASH_MEM : 11,
    OVERFLOW : 12
}

LOGGING_TABLE_REV = {v: k for k, v in LOGGING_TABLE.items()}

# DOMAIN means part of the system or aspect like SERVICE or CPU or UNKNOWN

def domain_to(domain: str | int, byte=False):
    """
    Convert domain name <-> int <-> bytes.
    """
    if byte:
        if isinstance(domain, str):
            if domain in LOGGING_TABLE:
                return LOGGING_TABLE[domain].to_bytes(1, "big")  # int -> byte
            return b""
        elif isinstance(domain, int):
            if domain in LOGGING_TABLE_REV:
                return LOGGING_TABLE_REV[domain].encode("utf-8")  # str -> bytes
            return b""
        else:
            return b""

    # Non-byte mode
    if isinstance(domain, str) and domain in LOGGING_TABLE:
        return LOGGING_TABLE[domain]
    elif isinstance(domain, int) and domain in LOGGING_TABLE_REV:
        return LOGGING_TABLE_REV[domain]

    return None

# DOMAIN | LEVEL | ( NAME | RESOLVER | AUTO_RESOLVE )
ERROR_TABLE = {
    UNKNOWN : {
        LVL_OFF : ("UNKNOWN",None,False),
        LVL_FATAL : ("UNKNOWN",None,False),
        LVL_CRITICAL : ("UNKNOWN",None,False),
        LVL_WARN : ("UNKNOWN",None,False),
        LVL_INFO : ("UNKNOWN",None,False),
        LVL_DEBUG : ("UNKNOWN",None,False),
        LVL_UNKNOWN : ("UNKNOWN",None,False),
    },
}

def getError(severity, code):
    """
    Retrieve error details based on both severity and code.
    """
    if code in ERROR_TABLE and severity in ERROR_TABLE[code]:
        return ERROR_TABLE[code][severity]
    return None

# Storage locations of data and logs
FILE_DATA         = const("data.bin")
FILE_DATA_TEMP    = const("data.temp.bin")
FILE_LOG          = const("log.bin")
FILE_LOG_TEMP     = const("log.temp.bin")


# Communications
#--------------------------------------------------------------------------

# Constants (Packet Headers)
CMD_ACTION = 0x01
CMD_RESPONSE = 0x02
CMD_ACK = 0x03
CMD_MODE = 0x10
CMD_DATA = 0x11
CMD_ERROR = 0xEE

# Predefined Modes
MODE_COMMAND = 0x01
MODE_HEALTH = 0x02
MODE_TELEMETRY = 0x03

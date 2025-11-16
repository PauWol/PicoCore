from micropython import const
import ustruct

# --------------------- Old config ---------------------
# TODO: Needs to be revised
# Power modes
PM_ACTIVE = const("ACTIVE")
PM_IDLE = const("IDLE")
PM_ECO = const("ECO")
PM_LIGHT_SLEEP = const("LIGHT_SLEEP")
PM_DEEP_SLEEP = const("DEEP_SLEEP")
PM_OFF = const("OFF")

PM_LIST = [PM_ECO,PM_ACTIVE,PM_OFF,PM_IDLE,PM_LIGHT_SLEEP,PM_DEEP_SLEEP]


NORMALIZED_VOLTAGE_DIFFERENCE_V_MAX_TO_V_NOMINAL = 0.1
NORMALIZED_VOLTAGE_MARGIN_V_CUT_OFF_TO_V_NOMINAL = 0.2


# --------------------- Configuration ---------------------

POWER_MONITOR_ENABLED = const("power.monitoring.enabled")
POWER_BATTERY_VOLTAGE_MAX = const("power.battery.battery_voltage_max")
POWER_BATTERY_VOLTAGE_NOMINAL = const("power.battery.battery_voltage_nominal")
POWER_BATTERY_AH = const("power.battery.battery_ah")
POWER_BATTERY_VOLTAGE_CUT_OFF = const("power.battery.battery_voltage_cut_off")
POWER_ADC_PIN = const("power.battery.adc_pin")

POWER_VOLTAGE_DIVIDER_ENABLED = const("power.voltage_divider.enabled")
POWER_VOLTAGE_DIVIDER_R1 = const("power.voltage_divider.r1")
POWER_VOLTAGE_DIVIDER_R2 = const("power.voltage_divider.r2")



SLEEP_INTERVAL = const("system.runtime.interval")
# root rules




# --------------------- Event Bus ---------------------

BUS_SYSTEM_ROOT_PATH = const("system/root")
BUS_SYSTEM_POWER_PATH = const("system/root/power")


EVENT_ROOT_LOOP_TICK = const("root/loop/tick")

EVENT_ROOT_LOOP_BOOT_BEFORE = const("root/loop/boot/before")
EVENT_ROOT_LOOP_BOOT_AFTER = const("root/loop/boot/after")
EVENT_ROOT_LOOP_BOOT = const("root/loop/boot")


# --------------------- Boot ---------------------

BOOT_FLAG = "boot_flag"      # filename stored in flash
BOOT_WINDOW_MS = 1500        # time window to consider a second boot as "double boot"


# --------------------- Logging ---------------------

# Levels as small ints (cheap comparisons)
OFF = const(0)
FATAL = const(1)
ERROR = const(2)
WARN = const(3)
INFO = const(4)
DEBUG = const(5)
TRACE = const(6)

# Map names (optional)
LEVEL_NAMES = {
    FATAL: "FATAL", ERROR: "ERROR", WARN: "WARN",
    INFO: "INFO", DEBUG: "DEBUG", OFF: "OFF", TRACE: "TRACE"
}


LEVEL_BYTES = {
    OFF:   ustruct.pack('B', OFF),
    FATAL: ustruct.pack('B', FATAL),
    ERROR: ustruct.pack('B', ERROR),
    WARN:  ustruct.pack('B', WARN),
    INFO:  ustruct.pack('B', INFO),
    DEBUG: ustruct.pack('B', DEBUG),
    TRACE: ustruct.pack('B', TRACE)
}

# File paths
LOG_FILE_PATH = const("logs.bin")
DATA_FILE_PATH = const("data.txt")

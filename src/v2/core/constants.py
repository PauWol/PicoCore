from micropython import const


# Power modes
PM_ACTIVE = const("ACTIVE")
PM_IDLE = const("IDLE")
PM_ECO = const("ECO")
PM_LIGHT_SLEEP = const("LIGHT_SLEEP")
PM_DEEP_SLEEP = const("DEEP_SLEEP")
PM_OFF = const("OFF")

PM_LIST = [PM_ECO,PM_ACTIVE,PM_OFF,PM_IDLE,PM_LIGHT_SLEEP,PM_DEEP_SLEEP]


BUS_SYSTEM_ROOT_PATH = const("system/root")
BUS_SYSTEM_POWER_PATH = const("system/root/power")


# configuration

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
# Root rules



NORMALIZED_VOLTAGE_DIFFERENCE_V_MAX_TO_V_NOMINAL = 0.1
NORMALIZED_VOLTAGE_MARGIN_V_CUT_OFF_TO_V_NOMINAL = 0.2
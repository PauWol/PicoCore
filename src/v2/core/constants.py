from micropython import const


# Power modes
PM_ACTIVE = const("ACTIVE")
PM_IDLE = const("IDLE")
PM_ECO = const("ECO")
PM_LIGHT_SLEEP = const("LIGHT_SLEEP")
PM_DEEP_SLEEP = const("DEEP_SLEEP")
PM_OFF = const("OFF")

PM_LIST = [PM_ECO,PM_ACTIVE,PM_OFF,PM_IDLE,PM_LIGHT_SLEEP,PM_DEEP_SLEEP]
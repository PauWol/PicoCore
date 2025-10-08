from v2.core.constants import PM_LIST
from v2.core import config

class Power:
    def __init__(self):
        self.monitoring = False
        self.voltage_divider = False
        self._init()


    def _init(self):
        if config.get_config("power.monitoring.enabled"):
            self.monitoring = True
            self.battery_voltage = config.get_config("power.battery_voltage")
            self.battery_ah = config.get_config("power.battery_ah")
            self.low_battery_warning = config.get_config("power.low_battery_warning")
            self.adc_pin = config.get_config("power.adc_pin")
            if config.get_config("power.voltage_divider.enabled"):
                self.voltage_divider = True
                self.R1 = config.get_config("power.voltage_divider.R1")
                self.R2 = config.get_config("power.voltage_divider.R2")
            else:
                self.voltage_divider = False
        else:

            self.monitoring = False
            self.voltage_divider = False



    def evaluate(self):
        pass

    def set_mode(self, mode):
        pass

    def get_mode(self) -> str:
        pass


    # Voltage Divider section

    def 
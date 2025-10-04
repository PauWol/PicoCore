from core.utils.error import raiseError, get_error_count_since_boot, reset_error_count_since_boot
from core.constants.constants import CPU, BOARD_TEMP, RAM, FLASH_MEM, OVERFLOW, SERVICE_START, SERVICE_STOP, LVL_FATAL, \
    LVL_CRITICAL, LVL_UNKNOWN
from core.logger import get_logger
from core.utils.system import BOARD_TEMP, BOARD_RAM_USAGE, BOARD_FLASH_USAGE, BOARD_CPU_LOAD, setCPUFrequency, RESET
from core.services.servicemanager import service_manager
from machine import Timer

class SystemHealth:
    def __init__(self,interval,hardware_cooling=False):
        self.hardware_cooling = hardware_cooling
        self.interval =  interval if interval is not None else 2500
        self.timer = None
        self._is_running = False
        self._temp_change = False
        self._freq_change = False
        self._ram_change = False
        self._mem_change = False

    def _temp(self):
        temp = BOARD_TEMP()
        # TODO: Add hardware cooling
        if temp < 0 :
            if temp < -10:
                self._temp_change = True
                raiseError(LVL_FATAL, BOARD_TEMP, f"Temperature too low {temp:.2f}°C")
            else:
                self._temp_change = True
                raiseError(LVL_CRITICAL, BOARD_TEMP, f"Temperature reaching {temp:.2f}°C")
        elif temp > 30:
            if temp > 40:
                self._temp_change = True
                raiseError(LVL_FATAL, BOARD_TEMP, f"Temperature too high {temp:.2f}°C")
            else:
                self._temp_change = True
                raiseError(LVL_CRITICAL, BOARD_TEMP, f"Temperature reaching {temp:.2f}°C")
        elif self._temp_change:
            self._temp_change = False
            raiseError(LVL_UNKNOWN,BOARD_TEMP, f"Temperature normal {temp:.2f}°C")

    def _cpu(self):
        """Check CPU usage."""
        load = BOARD_CPU_LOAD()

        if load > 80:
            get_logger().warn(CPU, f"CPU load at {load:.2f}% changing frequency","health.py:46")
            setCPUFrequency("high")
            self._freq_change = True
        elif load > 50 and self._freq_change:
            setCPUFrequency("normal")
            self._freq_change = False
        elif load < 50 and not self._freq_change:
            get_logger().info(CPU, f"CPU load at {load:.2f}% changing frequency","health.py:53")
            setCPUFrequency("low")
            self._freq_change = True

    def _ram(self):
        """Check RAM usage."""
        ram_usage, used_ram, total_ram = BOARD_RAM_USAGE()

        if ram_usage > 95:
            self._ram_change = True
            service_manager.mode("low")
            get_logger().warn(RAM, f"RAM {ram_usage:.2f}% changing to low mode","health.py:64")
        elif ram_usage > 80:
            self._ram_change = True
            service_manager.mode("medium")
            get_logger().info(RAM, f"RAM {ram_usage:.2f}% changing to medium mode","health.py:68")
        elif self._ram_change:
            self._ram_change = False
            service_manager.mode()
            get_logger().info(RAM, f"RAM {ram_usage:.2f}% changing to normal mode","health.py:72")

    def _mem(self):
        """Check flash memory usage."""
        flash_usage, used_flash, total_flash = BOARD_FLASH_USAGE()

        if flash_usage > 80:
            self._mem_change = True
            get_logger().mode("low")
            get_logger().warn(FLASH_MEM, f"Flash {flash_usage:.2f}% changing to low mode","health.py:81")
        elif flash_usage > 70:
            self._mem_change = True
            get_logger().mode("medium")
            get_logger().info(FLASH_MEM, f"Flash {flash_usage:.2f}% changing to medium mode","health.py:85")
        elif self._mem_change:
            self._mem_change = False
            get_logger().mode()
            get_logger().info(FLASH_MEM, f"Flash {flash_usage:.2f}% changing to normal mode","health.py:89")

    @staticmethod
    def _error():
        error_count = get_error_count_since_boot()
        if not error_count > 0:
            return

        if error_count >= 30:
            get_logger().warn(OVERFLOW, f"Error count limit reached {error_count}, restarting system","health.py:98")
            get_logger().cleanup()
            RESET()

        elif error_count >= 20:
            get_logger().info(OVERFLOW, f"Too many unresolved errors {error_count}, resetting services","health.py:103")
            service_manager.reset()
            service_manager.startAll()
            reset_error_count_since_boot()

        elif error_count >= 10:
            get_logger().info(OVERFLOW, f"Attention {error_count} unresolved errors, restarting services","health.py:109")
            service_manager.restartAll()
            reset_error_count_since_boot()




    def _check(self,timer):
        self._temp()
        self._cpu()
        self._ram()
        self._mem()
        self._error()

    def start(self):

        if self._is_running:
            return
        self._is_running = True
        self.timer = Timer()

        self.timer.init(period=self.interval, mode=Timer.PERIODIC, callback=self._check)
        get_logger().debug(SERVICE_START, "Health started","health.py:131")

    def stop(self):
        if self._is_running:
            self._is_running = False

            if self.timer:
                self.timer.deinit()
                get_logger().debug(SERVICE_STOP, "Health stopped","health.py:136")

if __name__ == "__main__":
    try:

        health = SystemHealth(2500)
        health.start()
    except Exception as e:
        print(e)

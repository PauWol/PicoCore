import time
import machine

from core.constants.constants import LVL_WARN, PARAMETER
from core.utils.error import raiseError


class LED:
    def __init__(self, led_pin: str | int = "LED", blink_mode: str = "idle",on_period: float = 0.5, off_period: float = 0.5):
        self.led_pin = machine.Pin(led_pin, machine.Pin.OUT)
        self.blink_mode = blink_mode
        self.is_blinking = False
        self.timer = None
        self.on_period = int(on_period * 1000)   # convert to ms
        self.off_period = int(off_period * 1000) # convert to ms
        self._led_state = 0  # track state for custom blinking

    def _get_blink_interval(self):
        """Return the interval for blinking based on the mode."""
        return {
            "error": 100,            # Very fast blink
            "power_safe": 50000,     # Long blink
            "pairing": 500,          # Double blink (handled separately)
            "idle": 2000,            # Very slow blink
            "connection_lost": 1000, # Slow blink
            "processing": 300,       # Medium-fast blink
        }.get(self.blink_mode, 1000)  # Default 1s if unknown mode

    def _toggle_led(self, timer):
        """Toggle LED for normal blinking modes."""
        self.led_pin.value(not self.led_pin.value())

    def _double_blink(self, timer):
        """Double blink pattern for pairing mode."""
        self.led_pin.value(1)
        time.sleep_ms(100)
        self.led_pin.value(0)
        time.sleep_ms(100)
        self.led_pin.value(1)
        time.sleep_ms(100)
        self.led_pin.value(0)

    def _custom_blink(self, timer):
        """Custom blink with on/off periods."""
        if self._led_state == 0:
            self.led_pin.value(1)
            self._led_state = 1
            self.timer.init(period=self.on_period, mode=machine.Timer.ONE_SHOT, callback=self._custom_blink)
        else:
            self.led_pin.value(0)
            self._led_state = 0
            self.timer.init(period=self.off_period, mode=machine.Timer.ONE_SHOT, callback=self._custom_blink)

    def start(self):
        """Start LED blinking based on mode."""
        if self.is_blinking:
            return  # Already running
        self.is_blinking = True

        self.timer = machine.Timer()
        if self.blink_mode == "pairing":
            self.timer.init(period=1000, mode=machine.Timer.PERIODIC, callback=self._double_blink)
        elif self.blink_mode == "custom":
            self._led_state = 0
            self._custom_blink(None)  # start cycle
        else:
            self.timer.init(period=self._get_blink_interval(),
                            mode=machine.Timer.PERIODIC,
                            callback=self._toggle_led)

    def stop(self):
        """Stop LED blinking."""
        if self.is_blinking:
            self.is_blinking = False
            if self.timer:
                self.timer.deinit()
            self.led_pin.value(0)  # Ensure LED is off

    def set_mode(self, new_mode):
        """Set a new LED blinking mode."""
        if new_mode not in ["error", "pairing", "idle", "connection_lost", "processing", "custom"]:
            raiseError(LVL_WARN, PARAMETER, f"Invalid LED mode {new_mode}")

        self.stop()
        self.blink_mode = new_mode
        time.sleep_ms(100)  # Short delay for smooth restart
        self.start()

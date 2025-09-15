import dht
import machine

from core.constants.constants import SERVICE_START
from core.logger import get_logger
from core.services.servicemanager import service_manager


class Weather_Station:
    def __init__(self, interval_min: int | float, dht_11_sensor=None):
        # Attach sensor
        self.dht_11_sensor = dht.DHT11(machine.Pin(0)) if dht_11_sensor is None else dht_11_sensor

        # Always store interval as float internally
        self.interval_min = float(interval_min)

        self.timer = None
        self._is_running = False

    def start(self):
        if self._is_running:
            return

        self._is_running = True

        self.timer = machine.Timer()
        # Convert minutes -> ms, ensure integer
        period_ms = int(self.interval_min * 60 * 1000)
        self.timer.init(period=period_ms, mode=machine.Timer.PERIODIC, callback=self._measure)

    def stop(self):
        if self._is_running:
            self._is_running = False
            if self.timer:
                self.timer.deinit()
                self.timer = None

    def _measure(self, timer):
        self.dht_11_sensor.measure()
        temperature = self.dht_11_sensor.temperature()
        humidity = self.dht_11_sensor.humidity()
        get_logger().data("Weather_Station", f"Temperature: {temperature}°C, Humidity: {humidity}%")

if __name__ == "__main__":
    # Register service with 0.2 min interval (~12s)
    service_manager.register("Weather_Station", 1, Weather_Station, 5)
    service_manager.startAll()
    get_logger().warn(SERVICE_START,"Weather_Station", "Main.py:40")

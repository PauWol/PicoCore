from ..constants import POWER_ADC_PIN, POWER_VOLTAGE_DIVIDER_R1, POWER_VOLTAGE_DIVIDER_R2, SLEEP_INTERVAL, \
    POWER_BATTERY_VOLTAGE_CUT_OFF, POWER_BATTERY_VOLTAGE_MAX, POWER_BATTERY_VOLTAGE_NOMINAL, POWER_BATTERY_AH, \
    NORMALIZED_VOLTAGE_DIFFERENCE_V_MAX_TO_V_NOMINAL, NORMALIZED_VOLTAGE_MARGIN_V_CUT_OFF_TO_V_NOMINAL
from ..IO import VoltageDivider
from ..config import get_config
from .queue import RingBuffer


class Power(VoltageDivider):
    def __init__(self):
        conf = get_config()
        super().__init__(
            conf.get(POWER_ADC_PIN),
            conf.get(POWER_VOLTAGE_DIVIDER_R1),
            conf.get(POWER_VOLTAGE_DIVIDER_R2)
        )

        self._sleep_interval = conf.get(SLEEP_INTERVAL)
        self._cut_off_voltage = conf.get(POWER_BATTERY_VOLTAGE_CUT_OFF)
        self._nominal_voltage = conf.get(POWER_BATTERY_VOLTAGE_NOMINAL)
        self._max_voltage = conf.get(POWER_BATTERY_VOLTAGE_MAX)
        self._voltage_buffer: RingBuffer | None = None
        self._time_left_buffer: RingBuffer | None = None

        self.init()

    @property
    def data(self):
        return {
            "voltage": self._voltage_buffer,
            "time_left": self._time_left_buffer
        }


    def init(self):
        self._voltage_buffer = RingBuffer(10, overwrite=True)
        self._time_left_buffer = RingBuffer(10, overwrite=True)

    async def check(self):
        return await self.async_check()

    def deinit(self):
        del self._voltage_buffer

    async def tick(self):
        """Tick function to be called at regular intervals."""
        print("Power tick")
        # Add the mean of the last 10 samples to the buffer per tick
        self._voltage_buffer.put(await self.async_mean_real_voltage(delay=0.5))
        self._time_left_buffer.put(self.estimate_time_left())
        print(self._voltage_buffer.peek_latest(), self._time_left_buffer.peek_latest())

        self.eval()

    def eval(self):
        pass

    def estimate_time_left(self):
        """Estimate time remaining until cutoff voltage.Time is in seconds."""
        current_voltage = self._voltage_buffer.peek_latest()

        if self.is_in_nominal_range(current_voltage):
            return None

        slopes, accel = self.slope_trend(self._voltage_buffer.to_list())

        if not slopes:
            return None  # not enough data

        current_slope = slopes[-1]  # latest dV/dt

        voltage_diff = self.calc_difference_to_cut_off()
        # estimate time (s)
        time_left = voltage_diff / current_slope

        # optional: refine using acceleration
        if len(accel) > 0:
            avg_accel = accel[-1]
            # rough correction if acceleration significant
            time_left *= avg_accel

        return time_left

    def calc_difference_to_cut_off(self):
        """
        Calculate the difference between the current voltage and the cutoff voltage.
        A positive value means the battery is above cutoff voltage.
        A negative value means the battery is below cutoff voltage.
        :return:
        """
        return self._cut_off_voltage - self._voltage_buffer.peek_latest()

    def calc_difference_to_nominal(self):
        """
        Calculate the difference between the current voltage and the nominal voltage.
        A positive value means the battery is above nominal voltage.
        A negative value means the battery is below nominal voltage.
        :return:
        """
        return self._nominal_voltage - self._voltage_buffer.peek_latest()

    def calc_difference_to_max(self):
        """
        Calculate the difference between the current voltage and the max voltage.
        A positive value means the battery is above max voltage.
        A negative value means the battery is below max voltage.
        :return:
        """
        return self._max_voltage - self._voltage_buffer.peek_latest()

    def is_in_nominal_range(self, voltage: float | int):
        """
        Check if the current voltage is within the nominal range.
        :return:
        """
        vn = self.normalize_voltage(voltage)
        vmt = 1 - NORMALIZED_VOLTAGE_DIFFERENCE_V_MAX_TO_V_NOMINAL

        if vmt > vn > NORMALIZED_VOLTAGE_MARGIN_V_CUT_OFF_TO_V_NOMINAL:
            return True
        return False

    def normalize_voltage(self, voltage: float | int):
        """
        Normalize the voltage to a value between 0 and 1.
        :param voltage:
        :return:
        """
        return (voltage - self._cut_off_voltage) / (self._max_voltage - self._cut_off_voltage)

    def slope_trend(self, values=None, dt=None):
        """
        Compute how the rate of change (slope) evolves over time.
        Returns:
            slopes: list of slope estimates per interval (V/s)
            accel:  list of acceleration estimates (change in slope) per interval (V/s²)
        """
        if values is None:
            values = self._voltage_buffer.to_list()
        if dt is None:
            dt = self._sleep_interval / 1000
        n = len(values)
        if n < 3:
            return [], []

        # first derivative (V/s)
        slopes = []
        inv_dt = 1.0 / dt
        for i in range(n - 1):
            slopes.append((values[i + 1] - values[i]) * inv_dt)

        # second derivative (V/s²)
        accel = []
        for i in range(len(slopes) - 1):
            accel.append((slopes[i + 1] - slopes[i]) * inv_dt)

        return slopes, accel




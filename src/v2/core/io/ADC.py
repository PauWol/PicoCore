from machine import ADC as HWADC, Pin
from uasyncio import sleep as async_sleep
from time import sleep
import math

from .Util import stats_from_samples


class ADC:
    def __init__(self, pin: int, vref: float = 3.3, scale: float = 1.0, offset: float = 0.0):
        """
        Initialize the ADC.

        :param pin: Pin number
        :param vref: Reference voltage
        :param resolution: ADC resolution
        :param scale: Scale factor
        :param offset: Offset value

        """
        self._pin = HWADC(Pin(pin))

        self._vref = vref
        self._scale = scale
        self._offset = offset

    def raw(self) -> int:
        """
        Return the raw ADC reading as u16 (range 0 - 65535).
        """
        return self._pin.read_u16()

    def voltage(self) -> float:
        """
        Convert the raw ADC reading to a voltage.

        Equation:
            voltage = (raw / 65535) * Vref

        Where:
            raw   = 16-bit ADC value from read_u16() (0–65535)
            Vref  = Reference voltage (self._vref)

        The result represents the measured input voltage in volts.
        """
        return (self.raw() / 65535) * self._vref

    def real(self) -> float:
        """Return scaled, real-world value (e.g., temperature, light intensity)."""
        return self.voltage() * self._scale + self._offset

    def _measure(self, type: str = "raw") -> float:
        """
        Helper method for the sample methods to make type param usage easier.
        """
        if type == "raw":
            return self.raw()
        elif type == "voltage":
            return self.voltage()
        elif type == "real":
            return self.real()
        else:
            return float("nan")

    def samples(self, n: int = 10, type: str = "raw", delay: float = 0.001) -> list[float]:
        """
        Return list of n samples (optionally with delay).

        :param n: Number of samples to return
        :param type: String of measurement method type can be "raw" | "real" | "voltage"
        :param delay: Delay between samples in seconds
        :return: List of n samples
        """
        data = []
        for _ in range(n):
            if delay:
                sleep(delay)
            data.append(self._measure(type))
        return data

    async def async_samples(self, n: int = 10, type: str = "raw", delay: float = 0.001) -> list[float]:
        """
        Return list of n samples (optionally with delay).
        :param n: Number of samples to return
        :param type: String of measurement method type can be "raw" | "real" | "voltage"
        :param delay: Delay between samples in seconds
        :return:  List of n samples
        """
        data = []
        for _ in range(n):
            if delay:
                await async_sleep(delay)
            data.append(self._measure(type))
        return data

    def mean(self, n: int = 10, type: str = "raw", delay: float = 0.001) -> float:
        """
        Mean wrapper for the samples function,hence the same parameters.
        :param n: Number of samples to gather and calculate for the average
        :param type: String of measurement method; type can be "raw" | "real" | "voltage"
        :param delay: Delay between samples in seconds
        :return:  average of the gathered samples in set type
        """
        readings = self.samples(n, type, delay)
        return sum(readings) / len(readings)

    async def async_mean(self, n: int = 10, type: str = "raw", delay: float = 0.001) -> float:
        """
        Mean wrapper for the async_samples function,hence the same parameters.
        :param n: Number of samples to gather and calculate for the average
        :param type: String of measurement method; type can be "raw" | "real" | "voltage"
        :param delay: Delay between samples in seconds
        :return average of the gathered samples in set type
        """
        readings = await self.async_samples(n, type, delay)
        avg_raw = sum(readings) / len(readings)
        return avg_raw

    def _is_pin_connected_heuristics(self, samples: list[float | int], allow_saturation_tol_v=0.05, max_noise_v=0.02,
                                     min_expected_v=None, max_expected_v=None) -> tuple[bool, dict]:
        cnt, mean, var, mn, mx = stats_from_samples(samples)
        if cnt == 0:
            return False, {"reason": "no_samples"}

        std = math.sqrt(var)

        # check saturation: mean very close to 0 or vref (or min/max of divider)
        saturated_low = (mean is not None and mean <= (0.0 + allow_saturation_tol_v))
        saturated_high = (self._vref is not None and mean >= (self._vref - allow_saturation_tol_v))

        # heuristics
        if saturated_low:
            return False, {"reason": "short_to_gnd", "mean": mean, "std": std, "min": mn, "max": mx}
        if saturated_high:
            return False, {"reason": "short_to_vcc", "mean": mean, "std": std, "min": mn, "max": mx}

        # floating detection: too noisy or wide range relative to expected noise
        if std > max_noise_v or (mx - mn) > (max_noise_v * 3):
            # mid-range + noisy -> likely floating
            # If mean is roughly mid-range (not near 0 or vref) and noise large => floating
            return False, {"reason": "floating_or_noisy", "mean": mean, "std": std, "min": mn, "max": mx}

        # expected range check if provided
        if (min_expected_v is not None and mean < min_expected_v - max_noise_v) or \
                (max_expected_v is not None and mean > max_expected_v + max_noise_v):
            return False, {"reason": "out_of_expected_range", "mean": mean, "std": std, "min": mn, "max": mx}

        # otherwise assume connected & stable
        return True, {"reason": "ok", "mean": mean, "std": std, "min": mn, "max": mx}

    def is_pin_connected(self, n=20, delay=0.001, allow_saturation_tol_v=0.05, max_noise_v=0.02, min_expected_v=None,
                         max_expected_v=None) -> tuple[bool, dict]:
        """
        Heuristic check whether the ADC pin is connected to a stable source.
        Returns (connected: bool, details: dict).

        Parameters:
          n                - number of samples to collect (sync)
          delay            - seconds between samples when sampling
          allow_saturation_tol_v - voltage tolerance near 0 or vref to detect short
          max_noise_v      - if signal stddev (sqrt(var)) > this -> likely floating
          min_expected_v   - if provided, mean must be >= this
          max_expected_v   - if provided, mean must be <= this
        """
        # 1. Collect data

        try:
            samples = self.samples(n, "voltage", delay)
        except Exception as e:
            return False, {"error": "read_failed", "exception": str(e)}

        return self._is_pin_connected_heuristics(samples, allow_saturation_tol_v, max_noise_v, min_expected_v,
                                                 max_expected_v)

    async def async_is_pin_connected(self, n=20, delay=0.001, allow_saturation_tol_v=0.05, max_noise_v=0.02,
                                     min_expected_v=None, max_expected_v=None) -> tuple[bool, dict]:
        """
        Heuristic check whether the ADC pin is connected to a stable source.
        Returns (connected: bool, details: dict).

        Parameters:
          n                - number of samples to collect (sync)
          delay            - seconds between samples when sampling
          allow_saturation_tol_v - voltage tolerance near 0 or vref to detect short
          max_noise_v      - if signal stddev (sqrt(var)) > this -> likely floating
          min_expected_v   - if provided, mean must be >= this
          max_expected_v   - if provided, mean must be <= this
        """
        # 1. Collect data

        try:
            samples = await self.async_samples(n, "voltage", delay)
        except Exception as e:
            return False, {"error": "read_failed", "exception": str(e)}

        return self._is_pin_connected_heuristics(samples, allow_saturation_tol_v, max_noise_v, min_expected_v,
                                                 max_expected_v)


class VoltageDivider(ADC):
    def __init__(self, adc_pin: int, r1: float, r2: float, vref: float = 3.3, scale: float = 1.0, offset: float = 0.0):
        """
        Initialize the voltage divider.

        :param adc_pin: ADC pin number
        :param r1: Resistance of the first resistor
        :param r2: Resistance of the second resistor
        :param vref: Reference voltage
        :param resolution: ADC resolution
        :param scale: Scale factor
        :param offset: Offset value
        """
        super().__init__(adc_pin, vref, scale, offset)
        self.r1 = r1
        self.r2 = r2

    def real_voltage(self) -> float:
        """
        Return the real voltage of the voltage divider.

        :return: Real voltage
        """
        v = self.voltage() * (self.r1 + self.r2) / self.r2
        print("rvol", v)
        return v

    async def async_mean_real_voltage(self, n: int = 10, delay: float = 0.001) -> float:
        """Return average real voltage of n samples."""
        readings = await self.async_samples(n, "voltage", delay)
        avg_raw = sum(readings) / len(readings)
        v = avg_raw * (self.r1 + self.r2) / self.r2
        print(v)
        return v


# Getting Started with the ADC Class

This guide explains how to use the `ADC` class to read analog signals from a Raspberry Pi Pico or Pico W and convert them to voltage or real-world values.

---

## Initialization

### 1. Create an ADC instance

```python
from core.io import ADC

# Example: pin 26, no extra vref, scaling or offset
adc = ADC(pin=26)
```

### Parameters

=== "Required"
            
     * {==**pin**==}: GPIO pin number connected to the analog signal.

=== "Optional"
        
    * {==**vref**==}: Reference voltage for conversion (default 3.3V).

=== "Advanced/Useful"

      * {==**scale**==}: Multiplier for real-world conversion (default 1.0).
      * {==**offset**==}: Offset added after scaling (default 0.0).

    !!! info "Calibration"
        The {==**scale**==} and {==**offset**==} values can be used to calibrate the ADC to match your specific application.
        Better to use the calibration function `adc.calibrate(real voltge)` instead.This requires a known real-world value to be provided.

## Reading Values

### 2. Raw ADC Reading

```python
raw_value = adc.raw()
print(f"Raw ADC: {raw_value}")
```

* Returns a value between 0 and 65535.

### 3. Voltage Measurement

```python
v = adc.voltage()
print(f"Voltage: {v:.2f} V")
```


* Converts the raw reading into volts.

??? info "Equation: Calculating Voltage"
    The equation for voltage conversion is:
    $$
    Voltage = \frac{\text{raw}}{65535} \cdot V_{\text{ref}}
    $$

    the {==**raw**==} value is the raw reading from the ADC as an integer between 0 and 65535 (*read_u16*), and {==**Vref**==} is the reference voltage in volts.

### 4. Real-World Value

```python
real_value = adc.real()
print(f"Scaled value: {real_value}")
```

* Applies scaling and offset to get real-world units (like temperature or light intensity).

---

## Sampling

### 5. Collect Multiple Samples

```python
samples = adc.samples(n=10, type='voltage', delay=0.01)
print(samples)
```

* `n`: number of samples
* `type`: `raw`, `voltage`, or `real`
* `delay`: seconds between samples

### 6. Asynchronous Sampling

```python
samples = await adc.async_samples(n=10, type='real')
print(samples)
```

### 7. Mean Value

```python
avg = adc.mean(n=10, type='voltage')
print(f"Average voltage: {avg:.2f} V")
```

* Use `async_mean` for asynchronous calculation.

---

## Pin Connection Check

### 8. Check if Pin is Connected

```python
connected, info = adc.is_pin_connected(n=20, delay=0.001)
print(connected, info)
```

* Returns a boolean and a dictionary with details.
* Detects floating, short-to-GND, or short-to-VCC conditions.

### 9. Asynchronous Check

```python
connected, info = await adc.async_is_pin_connected(n=20)
print(connected, info)
```

---

## Notes & Tips

* Use `voltage()` for direct voltage readings.
* Use `real()` for calibrated real-world measurements.
* Sampling with delay improves stability.
* Connection heuristics help avoid unreliable readings.

---

## External Resources

* [MicroPython ADC Documentation](https://docs.micropython.org/en/latest/library/machine.ADC.html)
* [Raspberry Pi Pico Datasheet](https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf)

---

## What’s Next?

* Learn about [Asynchronous Tasks and uasyncio](concepts/async.md)
* Explore [Sensor Integration with PicoCore](concepts/sensors.md)

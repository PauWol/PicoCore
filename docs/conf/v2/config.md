# PicoCore Configuration Guide

PicoCore uses a single `config.toml` file to configure system behavior, hardware features, logging, power management, and runtime options. This guide provides an overview of all available configuration fields and how to use them.

---

## Overview

Place a `config.toml` file in the root of your PicoCore project. During startup, PicoCore automatically loads and parses the file to configure runtime behavior.

This allows you to:

* Enable and configure the logger
* Adjust runtime loop speed
* Manage power monitoring and battery behavior
* Configure health checks and device indicators

---

## Full Example Configuration

Below is a full example demonstrating all available configuration fields:

```toml
[system]

[system.logger]
level = "INFO"
buffersize = 5
# int (bytes) or string with suffix ("1b", "1kb", "1mb")
max_file_size = "64kb"
log_to_console = true
log_to_file = true
max_rotations = 3

[system.health]
onboard_status_led = false
check_interval = 5000

[system.runtime]
interval = 0.1 # in seconds

[power]

[power.monitoring]
enabled = true

[power.battery]
battery_voltage_max = 5.5        # Volts
battery_voltage_nominal = 5      # Volts
battery_voltage_cut_off = 3.3    # Volts
battery_ah = 2.4                 # Ampere-hours
adc_pin = 28                     # ADC pin for voltage measurement
min_runtime = 10                 # minimum runtime in minutes

[power.voltage_divider]
enabled = true
r1 = 10_000  # Resistance of R1 in Ohms
r2 = 5_100  # Resistance of R2 in Ohms
```

---

## Configuration Sections

### `[system]`

Top-level system configuration.

#### `[system.logger]`

Controls how PicoCore logs data.

* **level**
    
    One of `OFF`, `FATAL`, `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`

    ```toml
        level = "INFO"
    ```


* **buffersize**
    
    Buffer size for log entries in RAM.

    ```toml
        buffersize = 5
    ```

    With this meaning `buffersize * 45 bytes`, where 45 bytes is the estimated size of a *small* log entry.

!!! warning "RAM vs. Flash"
    The `buffersize` is for RAM, the `max_file_size` is for Flash.
    
    If RAM is full, logs are flushed to disk. If Flash is full, the oldest log file is deleted.
    When  `FATAL` , `ERROR` , or `WARN` logs are logged, the log buffer is flushed to disk immediately.

* **max_file_size**
    
    Maximum log file size before rotation.
    Can either be:
    
    - an integer *(`bytes`)* 

    ```toml
    max_file_size = 64_000
    ```

    - or a string with suffix *(`1b`, `1kb`, `1mb`)*.

    ```toml
    max_file_size = "64kb"
    ```

    

* **log_to_console**
    
    Whether to output logs to REPL/serial.

    ```toml
        log_to_console = true
    ```

* **log_to_file**

    Whether to save logs to filesystem.

    ```toml
        log_to_file = true
    ```

* **max_rotations**

    Number of rotated log files to keep.

    ```toml
        max_rotations = 3
    ```

    Meaning that 3 rotated log files will be kept before the oldest is deleted.


#### `[system.runtime]`

Configures the main runtime loop.

* **interval**: Loop delay in seconds

---

### `[power]`

Power management configuration.

#### `[power.monitoring]`

* **enabled**: Turns power monitoring on/off

!!! warning "Power Monitoring"
    If enabled, PicoCore will use dynamic sleep to save power.Meaning it will go into a light sleep when idle.

    **Planned**: Support for deep sleep with state saving.


---

## Tips

* Values like `"64kb"` or `"1mb"` can simplify storage configuration.
* For all configurable fields, there is a default value if not specified or on Failure.

---

## Conclusion

The `config.toml` file provides a flexible way to tailor PicoCore's behavior without modifying code. Adjust it according to your device setup, application logic, and power requirements.

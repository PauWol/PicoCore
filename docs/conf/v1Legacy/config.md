This file deals with the structure of the configuration file written in TOML format for the OS.

# Example

```TOML
# PiScout Rover Configuration File

[system]
name = "PiScout Rover"
version = "1.0"
enable_logging = true
debug_mode = false

[system.logger]
level = "INFO"
buffersize = 8
max = 50
debug = false

[network]

[network.bluetooth]
enabled = true
ssid = "Test"
key = false
password = ""


[network.wlan]
enabled = false
password = "test"
ssid = "test"

[motors]
# Motor A - Left Wheel
[motors.left]
pwm_pin = 15
dir_pin = 14
speed_limit = 100  # Max 100%

# Motor B - Right Wheel
[motors.right]
pwm_pin = 17
dir_pin = 16
speed_limit = 100  # Max 100%

[sensors]
# Ultrasonic Distance Sensor
[sensors.ultrasonic]
trigger_pin = 10
echo_pin = 11
max_distance = 200  # cm

# IMU (Accelerometer + Gyro)
[sensors.imu]
i2c_sda = 4
i2c_scl = 5
sampling_rate = 50  # Hz

[power]
battery_voltage = 7.4  # Volts
low_battery_warning = 6.5  # Volts

[logging]
log_to_console = true
log_to_file = true
log_level = "INFO"  # Options: "DEBUG", "INFO", "WARNING", "ERROR"
log_file = "/logs/piscout.log"

```

# Getting Started with PicoCore

This guide helps you set up PicoCore from scratch, flash your board, and run your first program. It assumes you are using **Raspberry Pi Pico** or **Pico W**.

---

## Quickstart (5 minutes)

### 1. Download PicoCore release

- Go to the [releases](https://github.com/PauWol/PicoCore/releases) page.
- Download the latest `.zip` or `.7z` archive.
- Inside the archive you will usually find:

  - `README.md` or `instructions.txt`
  - precompiled `.mpy` libraries (the PicoCore API/runtime)
  - a matching MicroPython `.uf2` firmware file _(sometimes)_
  - some sort of **_hello world_** project in form of a `boot.py` and `main.py`

### 2. Flash MicroPython firmware

!!! tip "Tip: BOOTSEL mode"

To enter bootloader mode, hold {==BOOTSEL==} on your Pico/Pico W and plug it into your PC.

1. Your board will mount as a **RPI-RP2** drive.
2. Copy the `.uf2` firmware file onto it.
3. If no `.uf2` is included in the release, check the version in the `.version` file *(highlited line)* inside the `core` folder and download from [micropython.org](https://micropython.org/download/rp2-pico/).
```py title=".version" hl_lines="2"
2.0.0
1.26.1
```
4. The board will reboot automatically.

### 3. Copy PicoCore runtime

=== "Thonny"
    1.  Open Thonny → File → Upload to /.
    2.  Copy the pico_core/ folder and any config.toml, boot.py, or main.py files.

=== "mpremote"
    ```bash
    mpremote connect list
    mpremote connect <your-port> cp -r pico_core
    mpremote connect <your-port> cp config.toml boot.py main.py
    ```
=== "Helper Script"
    
    !!! warning "Disclaimer: No helper script there yet."


### 4. Verify installation

Open a REPL and test:

```python
import core
print(core.version())
```

✅ If you see a version string, PicoCore is working.

[Continue: First Program →](#first-program)

---

## First Program

Let’s blink the onboard LED using PicoCore APIs.

```python
from core.gpio import LED
import time

led = LED()

for i in range(5):
    led.on()
    time.sleep(0.5)
    led.off()
    time.sleep(0.5)
```

If the LED blinks five times, your setup is correct.

!!! success "Congratulations!"
You have successfully installed and tested PicoCore.

---

## Configuration

PicoCore can be customized via `config.toml`.

```toml
[logging]
level = "info"

[network]
wifi_ssid = "MyWiFi"
wifi_password = "secret123"
```

See the [Configuration Guide](conf/overview.md) for details.

!!! warning "Version differences"
Different PicoCore releases may ship with slightly different `config.toml` defaults. Always check the `README` in your release archive.

---

## External Resources

- [MicroPython Documentation](https://docs.micropython.org/)
- [Thonny IDE](https://thonny.org/)
- [mpremote tool](https://docs.micropython.org/en/latest/reference/mpremote.html)
- [Raspberry Pi Pico Datasheet](https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf)

---

## What’s Next?

- Learn about [Services and Tasks](concepts/services.md)
- Configure PicoCore with [conf.toml](conf/overview.md)

# PicoCore API Naming Conventions & Design Standards

## 🧭 Philosophy

PicoCore follows a minimal, expressive, and deterministic API design philosophy. Every class, method, and constant should communicate **intent and behavior clearly** while remaining **compact and consistent**.

### Goals

* Keep method names **one-worded** when possible.
* Prefer **verbs for actions** (e.g., `start()`, `stop()`, `read()`), **nouns for properties** (e.g., `state`, `voltage`).
* Favor **clarity over abstraction**, **simplicity over hierarchy**.
* APIs should be **discoverable**, **consistent**, and **orthogonal**.

---

## 🧩 File & Module Structure

Each hardware or service interface resides in its own module, named after its core functionality.

**Examples:**

```
/core/drivers/adc.py
/core/drivers/i2c.py
/core/services/logger.py
/core/services/scheduler.py
```

### Naming Pattern

| Type                | Pattern         | Example                                 |
| ------------------- | --------------- | --------------------------------------- |
| File                | lowercase       | `adc.py`                                |
| Class               | PascalCase      | `ADC`, `LoggerService`                  |
| Function            | snake_case      | `read_raw()`, `set_mode()`              |
| Method (Public API) | short lowercase | `start()`, `stop()`, `read()`, `real()` |
| Constant            | UPPERCASE       | `DEFAULT_VREF = 3.3`                    |

---

## ⚙️ Core API Design Rules

### 1. Class Design

Each driver or service should be **self-contained** and **single-purpose**, exposing a minimal API surface.

```python
class ADC:
    def __init__(self, pin, vref=3.3, r1=0.0, r2=1.0):
        self.pin = pin
        self.vref = vref
        self.r1 = r1
        self.r2 = r2

    def raw(self):
        """Return raw ADC reading (0–65535)."""
        ...

    def voltage(self):
        """Return measured voltage at ADC pin."""
        ...

    def real(self):
        """Return corrected external voltage (e.g., before divider)."""
        ...

    def mean(self, samples=10):
        """Return averaged voltage over N samples."""
        ...
```

### 2. Method Naming

| Type        | Description               | Example                                  |
| ----------- | ------------------------- | ---------------------------------------- |
| Action      | Performs operation        | `start()`, `stop()`, `reset()`           |
| Reader      | Returns state/value       | `read()`, `raw()`, `voltage()`, `real()` |
| Writer      | Modifies internal state   | `set_mode()`, `configure()`              |
| Computation | Returns calculated result | `mean()`, `delta()`                      |

---

## 🌿 Naming Style Examples

### Hardware Drivers

| Purpose | Class | Methods                                  |
| ------- | ----- | ---------------------------------------- |
| ADC     | `ADC` | `raw()`, `voltage()`, `real()`, `mean()` |
| GPIO    | `Pin` | `high()`, `low()`, `toggle()`, `state()` |
| PWM     | `PWM` | `start()`, `duty()`, `freq()`            |
| I2C     | `I2C` | `scan()`, `read()`, `write()`            |

### Services

| Purpose        | Class           | Methods                                  |
| -------------- | --------------- | ---------------------------------------- |
| Logger         | `Logger`        | `info()`, `warn()`, `error()`, `fatal()` |
| Task Scheduler | `Scheduler`     | `add()`, `remove()`, `run()`             |
| Error Manager  | `ErrorRegistry` | `register()`, `resolve()`, `emit()`      |

---

## 🔧 Functional Design

### Keep method names predictable and parallel across drivers:

```python
adc.voltage()
pwm.freq()
pin.state()
i2c.read()
```

Each method directly corresponds to the hardware behavior.

---

## 📘 Documentation Standards

* **Docstrings:** Use one-line summaries and optional extended sections.
* **Type Hints:** Required for all function signatures.
* **Units:** Always specify units in docstrings (e.g., `voltage() -> float  # in volts`).

**Example:**

```python
def voltage(self) -> float:
    """Return measured voltage (in volts)."""
    return (self.raw() / self._max) * self.vref
```

---

## 🧠 API Behavior Rules

* Avoid hidden state changes.
* Functions must be deterministic where possible.
* Always fail gracefully — raise or return an error object, never crash the system.

---

## 🧩 Example Unified Style

```python
# PicoCore Driver Example
from core.drivers.adc import ADC
from core.services.logger import Logger

adc = ADC(26, r1=10000, r2=10000)
log = Logger()

value = adc.real()
log.info(f"Battery Voltage: {value:.2f}V")
```

---

## 🏗️ Future-Proofing Guidelines

1. Always add new methods in a backward-compatible way.
2. Maintain symmetry: if there’s a `read()`, there should be a `write()` when appropriate.
3. Ensure naming remains meaningful when used across hardware layers.

**Example:**

```python
# Good
sensor.read()

# Bad
sensor.getData()
```

---

## 🧭 Summary

| Concept      | Rule                      |
| ------------ | ------------------------- |
| File names   | lowercase                 |
| Class names  | PascalCase                |
| Method names | lowercase, one-word verbs |
| Constants    | UPPERCASE                 |
| Docstrings   | Short and clear           |
| Determinism  | Always preferred          |
| Failures     | Graceful, never crash     |

---

**PicoCore Standard** — Designed for elegance, predictability, and minimalism.

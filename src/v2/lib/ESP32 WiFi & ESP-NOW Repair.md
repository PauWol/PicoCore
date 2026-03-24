# ESP32 WiFi / ESP-NOW "Out of Memory" Fix

## Problem

On **MicroPython (ESP32)** you may encounter errors like:

```text
wifi: Expected to init 10 rx buffer, actual is 0/4
esp_netif_new_api: Failed to configure netif (duplicate key)
OSError: WiFi Out of Memory
```

This usually happens when:

* WiFi / ESP-NOW is initialized **multiple times**
* The driver is left in a **half-initialized state**
* Heap memory becomes **fragmented before WiFi init**
* WLAN / ESPNow objects are **reused after failure**
* The ESP32 **loses power at a critical moment** during WiFi/ESP-NOW initialization

After this, even simple WiFi calls fail until a **full reset, hard reset, or reflash**.

---

## Recommended Strategy

The most reliable fix is to **run the repair step at the very start of `boot.py`**, before any other logic.

### Steps:

1. At the top of your `boot.py`, add:

```python
from esp_repair import wifi_espnow_repair

wifi_espnow_repair()
```

2. Copy `esp_repair.py` to the **same directory level as `boot.py`**.

3. **Test your system**:

   * If the repair fixes the problem, you can **remove the repair call** after a successful boot.
   * If the problem persists (dirty fix), **leave the repair in `boot.py`**.

4. If issues remain after adding the repair:

   * Remove other logic from `boot.py` and `main.py` to isolate WiFi initialization
   * Perform a **full power cycle** or **hard reset**
   * Reintroduce your main code step by step, keeping the repair at the top until stability is confirmed

---

## What the Repair Does

* Fully disables **STA + AP interfaces**
* Forces **garbage collection**
* Reinitializes WiFi cleanly
* Starts ESP-NOW in a safe state

This ensures:

* No leftover driver state
* No duplicate netif errors
* Enough contiguous memory for WiFi buffers

---

## When to Use

* `WiFi Out of Memory`
* `esp_netif_new_api failed`
* Random WiFi init failures after code changes
* ESP-NOW stops working
* After an **unexpected power loss** during initialization

---

## Notes

* ESP32 + MicroPython memory handling can be fragile, especially with:

  * `uasyncio` or other async systems
  * Mesh / networking stacks
  * Large object allocations before WiFi init

* Avoid **unplugging power during WiFi/ESP-NOW initialization**.

* The repair is **non-destructive** and safe to run multiple times.

* Running the repair **before any other logic** in `boot.py` gives the best chance of stable WiFi and ESP-NOW initialization.

---

## TL;DR

For persistent WiFi/ESP-NOW memory issues:

1. Put `wifi_espnow_repair()` at the **top of `boot.py`**
2. If stable, remove the repair call
3. If unstable, leave it, isolate other code, and perform a **hard reset / power cycle**

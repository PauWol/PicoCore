from ubluetooth import BLE
from micropython import const
import time
import ubinascii

# Event constants
_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_ADV_TYPE_NAME = const(9)  # Complete Local Name

class Bluetooth:
    def __init__(self):
        self._ble = BLE()
        self._ble.active(True)

        # user-registered callbacks (event_name -> function list)
        self._user_callbacks = {}

        # built-in system callbacks
        self._class_callbacks = {
            "scan": self._on_scan_result,
            "scan_done": self._on_scan_done,
        }

        # initialize scan results
        self._scan_results = []
        self._scanning_done = False

        # register MicroPython BLE IRQ handler
        self._ble.irq(self._irq_handler)

    def on_event(self, event, callback):
        """ Register a user-defined callback for an event """
        if event not in self._user_callbacks:
            self._user_callbacks[event] = []
        self._user_callbacks[event].append(callback)

    def remove_event(self, event, callback):
        """ Remove a previously registered callback """
        if event in self._user_callbacks:
            try:
                self._user_callbacks[event].remove(callback)
            except ValueError:
                print(f"[WARN] Callback not found for {event}")

    def _irq_handler(self, event, data):
        """ Handle incoming events and trigger appropriate callbacks """
        if event == _IRQ_SCAN_RESULT:  # scan result
            addr_type, addr, adv_type, rssi, adv_data = data
            self._trigger("scan", data)
        elif event == _IRQ_SCAN_DONE:  # scan done
            self._trigger("scan_done", data)
        elif event == _IRQ_CENTRAL_CONNECT:  # central connect
            conn_handle, addr_type, addr = data
            self._trigger("connect", data)
        elif event == _IRQ_CENTRAL_DISCONNECT:  # central disconnect
            conn_handle, addr_type, addr = data
            self._trigger("disconnect", data)

    def _trigger(self, event_name, data):
        """ Trigger both system and user-defined callbacks """
        # Run system handler if defined
        if event_name in self._class_callbacks:
            try:
                self._class_callbacks[event_name](data)
            except Exception as e:
                print(f"[WARN] system callback {event_name} failed:", e)

        # Run all user callbacks
        if event_name in self._user_callbacks:
            for cb in self._user_callbacks[event_name]:
                try:
                    cb(data)
                except Exception as e:
                    print(f"[WARN] user callback for {event_name} failed:", e)

    @staticmethod
    def decode_name(adv_data):
        i = 0
        while i + 1 < len(adv_data):
            length = adv_data[i]
            if length == 0:
                break
            adv_type = adv_data[i + 1]
            if adv_type == _ADV_TYPE_NAME:
                return adv_data[i + 2:i + 1 + length].decode()
            i += 1 + length
        return None

    def _on_scan_result(self, data):
        addr_type, addr, adv_type, rssi, adv_data = data

        # Convert memoryviews to safe copies (bytes)
        addr_copy = bytes(addr)
        adv_data_copy = bytes(adv_data)

        # Optionally make address printable
        addr_str = ubinascii.hexlify(addr_copy, ":").decode()
        adv_data_copy = self.decode_name(adv_data_copy)
        # Store safe tuple
        self._scan_results.append((addr_type, addr_str, adv_type, rssi, adv_data_copy))

    def _on_scan_done(self, data):
        """ Default handler for when scanning is complete """
        pass

    def scan(self, duration_s=5):
        """Scan for BLE devices and wait until scanning is done."""
        self._scan_results.clear()
        self._scanning_done = False

        # Start scanning
        self._ble.gap_scan(duration_s * 1000)
        print("Scanning...")

        # Wait until done
        t_start = time.ticks_ms()
        while not self._scanning_done:
            time.sleep_ms(100)
            # Optional timeout fallback (double the expected duration)
            if time.ticks_diff(time.ticks_ms(), t_start) > (duration_s * 2000):
                print("Scan timeout!")
                break

        return self._scan_results

if __name__ == "__main__":
    bt = Bluetooth()

    # Start scanning
    results = bt.scan(5)
    print(f"Scan results: {results}")


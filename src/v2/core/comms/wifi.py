from network import WLAN, AUTH_WPA2_WPA3_PSK, AUTH_OPEN , STAT_WRONG_PASSWORD
from time import ticks_diff, ticks_ms, sleep_ms
from uasyncio import sleep_ms as async_sleep_ms

 # On some ports TimeoutError doesnt exists.
try:
    TimeoutError
except NameError:
    class TimeoutError(OSError):
        pass

class Wifi:
    def __init__(self, mode: str | None = None):
        """
        Init the Wifi-Class.

        :param mode: Can either be 'STA' (Station) or 'AP' (Access Point) or None (set later).
        """

        self.interface: WLAN | None = None
        self._mode = None
        self._timeout: int = 15  # Timeout for Wi-Fi connect.

        if mode is not None and mode not in ("STA", "AP"):
            raise ValueError(f"Wifi mode must be 'STA' or 'AP' not: {mode}")

        if mode == "STA":
            self.set_interface()
        if mode == "AP":
            self.set_interface(True)

    def _require_interface(self) -> None:
        if self.interface is None:
            raise RuntimeError("Interface not set. Call set_interface() first.")

    def set_interface(self, access_point: bool = False) -> None:
        """
        Set the interface mode to station (Wifi-Connect), when access_point is true then to Ap-Mode.
        :param access_point: Used to toggle to Ap-Mode.
        """
        if not access_point:
            self.interface = WLAN(WLAN.IF_STA)
            self._mode = WLAN.IF_STA

            return


        self._mode = WLAN.IF_AP
        self.interface = WLAN(WLAN.IF_AP)

    def set_power_mode(self,value: int) -> None:
        """
        Set the power mode of the Wi-Fi Interface.

        :param value: Can either be 0 (off), 1 (mid-saving) or 2 (high-saving)
        """
        self._require_interface()

        if value not in (0,1,2):
            raise ValueError("Power mode values can only be 0,1 or 2.")

        self.interface.config(pm=value)


    def set_hostname(self,name: str) -> None:
        """
        Set the dhcp-hostname of the Device

        :param name: The name to use
        """
        self._require_interface()

        self.interface.config(dhcp_hostname=name)


    def get_hostname(self) -> str:
        """
        Get the current dhcp hostname.

        :return: The hostname.
        """
        return self.interface.config("dhcp_hostname")

    def get_power_mode(self) -> int:
        """
        Get the current actively used power mode.

        :return:  The current mode as int. 0 (off), 1 (mid-saving) or 2 (high-saving).
        """
        self._require_interface()

        return self.interface.config("pm")

    def enable(self) -> None:
        """
        Activate the Wi-Fi Radio.
        :return:
        """
        self._require_interface()
        self.interface.active(True)

    def disable(self) -> None:
        """
        Deactivate the Wi-Fi Radio.
        :return:
        """
        self._require_interface()
        self.interface.active(False)

    def is_connected(self) -> bool:
        """
        Return the connection state of the Interface.
        :return:
        """
        self._require_interface()
        return self._mode == WLAN.IF_STA and self.interface.isconnected()

    def _connect(self,ssid: str, psk: str|None = None) -> None:
        self._require_interface()

        if self._mode != WLAN.IF_STA:
            raise ValueError("Please set WIFI-Interface to Station mode first.")

        if not self.interface.active():
            self.enable()

        self.interface.connect(ssid, psk)

    def connect(self, ssid: str, psk: str | None = None) -> None:
        """
        Connect to a WI-FI with given ssid and if password protected the psk.
        Wait till connected or timed out (blocking).

        :param ssid: The Wi-Fi's ssid.
        :param psk: And the password if needed.
        :return:
        """

        self._connect(ssid,psk)

        start = ticks_ms()
        timeout = self._timeout * 1000

        while ticks_diff(ticks_ms(), start) < timeout:
            if self.is_connected():
                return
            status = self.interface.status()

            if status < 0:
                if status == STAT_WRONG_PASSWORD:
                    raise RuntimeError("Wrong WiFi password")

                self.interface.disconnect()
                raise RuntimeError(f"WiFi failed early: {status}")
            sleep_ms(100)

        self.interface.disconnect()
        raise TimeoutError(f"WiFi connection timed out! Status: {self.interface.status()}")

    def disconnect(self) -> None:
        """"
        Disconnect from Wi-Fi (blocking).
        Raises TimeoutError after timeout.
        """
        self._require_interface()

        if self._mode != WLAN.IF_STA:
            return
        self.interface.disconnect()
        start = ticks_ms()
        timeout = self._timeout * 1000

        while ticks_diff(ticks_ms(), start) < timeout:
            if not self.is_connected():
                return
            sleep_ms(100)

        raise TimeoutError(f"WiFi disconnection timed out! Status: {self.interface.status()}")

    async def async_connect(self, ssid: str, psk: str | None = None) -> None:
        """
        Connect to a WI-FI.
        Asynchronously wait till connected or timed out.

        :param ssid: The Wi-Fi's ssid.
        :param psk: And the password if needed.
        :return:
        """
        self._connect(ssid,psk)

        start = ticks_ms()
        timeout = self._timeout * 1000

        while ticks_diff(ticks_ms(), start) < timeout:
            if self.is_connected():
                return
            status = self.interface.status()

            if status < 0:
                self.interface.disconnect()
                raise RuntimeError(f"WiFi failed early: {status}")
            await async_sleep_ms(100)

        self.interface.disconnect()
        raise TimeoutError(f"WiFi connection timed out! Status: {self.interface.status()}")

    async def async_disconnect(self) -> None:
        """"
        Disconnect from Wi-Fi.
        Raises TimeoutError after timeout.
        """
        self._require_interface()
        if self._mode != WLAN.IF_STA:
            return
        self.interface.disconnect()
        start = ticks_ms()
        timeout = self._timeout * 1000

        while ticks_diff(ticks_ms(), start) < timeout:
            if not self.is_connected():
                return
            await async_sleep_ms(100)

        raise TimeoutError(f"WiFi disconnection timed out! Status: {self.interface.status()}")

    def ip(self) -> tuple[str, str] | None:
        """
        Return network info such as ip and subnet.
        Works for both STA (client) and AP mode.

        :return: None or a Tuple like: ('192.168.0.2', '255.255.255.0')
        """
        self._require_interface()

        if self._mode == WLAN.IF_STA and not self.is_connected():
            return None

        if not self.interface.active():
            return None

        result = self.interface.ipconfig('addr4')

        # Guard against uninitialised AP address
        if not result or result[0] == '0.0.0.0':
            return None

        return result

    def wait_for_ip(self, timeout_ms: int = 5000) -> tuple[str, str]:
        """
        Block until the interface has a valid IP, or raise TimeoutError.
        Works for both STA and AP mode.

        :param timeout_ms: How long to wait in milliseconds.
        :return: (ip, subnet) tuple
        """
        start = ticks_ms()
        while ticks_diff(ticks_ms(), start) < timeout_ms:
            result = self.ip()
            if result:
                return result
            sleep_ms(100)
        raise TimeoutError(f"Interface never got a valid IP within {timeout_ms}ms")

    def access_point(self, ssid: str, psk: str | None = None) -> None:
        """
        Spawn an Access Point.

        :param ssid: The AP's Name.
        :param psk: The Password, if None its automatically open.
        :return:
        """
        self._require_interface()

        if not self._mode == WLAN.IF_AP:
            raise ValueError("Interface mode must be access_point to make one.")

        if not self.interface.active():
            self.enable()

        if psk and len(psk) < 8:
            raise ValueError(f"Access Pont Password must be at least 8 characters, current : {len(psk)}")

        if psk:
            self.interface.config(
                essid=ssid,
                password=psk,
                authmode=AUTH_WPA2_WPA3_PSK
            )

        else:
            self.interface.config(
                essid=ssid,
                authmode=AUTH_OPEN
            )

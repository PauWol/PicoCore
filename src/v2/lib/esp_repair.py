
def wifi_espnow_repair():
    """

    """
    import network
    from aioespnow import AIOESPNow
    import gc, time

    gc.collect()

    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    time.sleep_ms(200)

    sta.active(True)

    esp = AIOESPNow()
    esp.active(True)

    print("WiFi + ESPNow clean init OK")
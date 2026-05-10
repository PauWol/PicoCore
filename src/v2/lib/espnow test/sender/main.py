import network
import espnow
import time

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

e = espnow.ESPNow()
e.active(True)

peer = b"\xff\xff\xff\xff\xff\xff"  # broadcast
e.add_peer(peer)

while True:
    e.send(peer, b"test")
    print("sent")
    time.sleep(1)

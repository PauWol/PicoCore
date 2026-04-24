from core import start, task

from core.comms.mesh import mesh, mesh_callback
import asyncio

from machine import Pin
import neopixel

pin = Pin(38, Pin.OUT)

np = neopixel.NeoPixel(pin, 1)


def on():
    np[0] = (0, 150, 0)  # (R, G, B) → green
    np.write()


def off():
    np[0] = (0, 0, 0)  # off (like pixels.clear())
    np.write()


nodeid = 35812


@task(0, async_task=False, boot=True)
def init():
    mesh().rx_enable()


@mesh_callback
async def cbl(host, msg):
    print(f"{host}: {msg}")
    if msg == 1:
        on()
        await asyncio.sleep(1)
        off()
    await asyncio.sleep_ms(0)


@task("1s")
async def stat():
    print(mesh().stats())
    print(mesh()._neighbors)
    await mesh().async_send_data(nodeid, "1")


on()
from time import sleep

sleep(2)
off()

start()

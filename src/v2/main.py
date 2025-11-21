from core import start,task, ONBOARD_LED
from core.logging import logger
from core.io import VoltageDivider, Led
from machine import Pin
import dht

led = Led(ONBOARD_LED,Pin.OUT)
dt = dht.DHT11(Pin(1))
vd = VoltageDivider(28,10_000,5_100)

@task("10min")
async def measure():
    dt.measure()
    temp , hum = dt.temperature() , dt.humidity()
    vol = await vd.async_mean_real_voltage(20)
    logger().data("",f"{temp},{hum},{vol}")

@task("10min")
async def blink():
    await led.async_blink(2,1)

@task("",boot=True,parallel=True)
async def blink():
    await led.async_blink(4,1)

start()



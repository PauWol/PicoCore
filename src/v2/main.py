from core import start,task
from core.logging import logger
from core.io import VoltageDivider, Led
from machine import Pin
import dht

led = Led(2,Pin.OUT)
dt = dht.DHT11(Pin(1))
vd = VoltageDivider(28,10_000,5_100)

@task("10min")
async def measure():
    dt.measure()
    temp , hum = dt.temperature() , dt.humidity()
    vol = await vd.async_mean_real_voltage(20)
    logger().data("t,h,v",f"{temp},{hum},{vol}")

@task("10min")
async def blink():
    await led.async_blink(2,1)

@task("",boot=True,parallel=True)
async def blink():
    await led.async_blink(4,1)

start()


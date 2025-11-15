from core import start,task , logging
from core.io import VoltageDivider

vd = VoltageDivider(28,10_000,5_100)

@task("5s")
async def measure_voltage():
    v = await vd.async_mean_real_voltage()
    logging.logger().data("V:",v)

start()

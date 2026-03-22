from core import start, task

from core.comms.mesh import mesh
import asyncio

async def cbl(host, msg):
    print(f"{host}: {msg}")
    await asyncio.sleep(0)

mesh().start()

try:
    print("esp stats:", mesh().stats())
except Exception as e:
    print("esp.stats error:", e)

mesh().callback(cbl)
mesh().rx_enable()

@task(None,async_task=True,boot=True)
async def hell():
    await mesh().async_hello()
    print("hello sent")

node_id = 25892

@task("2s",False)
def dat():
    mesh().send_data(node_id,"TEST")


start()

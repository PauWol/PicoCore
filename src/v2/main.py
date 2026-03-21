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
print(mesh().node_id())

@task(None,async_task=True,boot=True)
async def hell():
    await mesh().async_hello()
    print("hello sent")

node_id = 39448

@task("2s")
async def dat():
        await mesh().async_wait_for_hello_ack(node_id)
        await mesh().async_send_data(node_id,"Test")

start()

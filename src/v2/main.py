from core import start, task, add_task

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


def print_task():
    print("Tested print")


@task(None, async_task=True, boot=True)
async def hell():
    await mesh().async_hello()
    print("hello sent")


@task("8s", False)
def stat():
    print(mesh().stats())
    print(mesh()._neighbors)
    add_task(print_task, 0, async_task=False, onetime=True)


start()

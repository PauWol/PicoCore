from core import start, task

from core.comms.mesh import mesh, mesh_callback
import asyncio


@task(0, async_task=False, boot=True)
def init():
    mesh().rx_enable()


@mesh_callback
async def cbl(host, msg):
    print(f"{host}: {msg}")
    await asyncio.sleep(0)


@task("8s", False)
def stat():
    print(mesh().stats())
    print(mesh()._neighbors)


start()

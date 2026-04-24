# This is the fle Sender
from core import start, task
from core.comms.mesh import mesh, mesh_callback


@task(0, async_task=False, boot=True)
def init():
    mesh().rx_enable()


@mesh_callback()
async def cbl(host, msg):
    print(f"{host}: {msg}")


NODE_ID = 35812
FILE_NAME = "logs.bin"
NEW_NAME = "logs-other.bin"


@task("5s", onetime=True)
async def send_file():
    print("Sending File")
    await mesh().async_send_file(NODE_ID, FILE_NAME, NEW_NAME)


start()

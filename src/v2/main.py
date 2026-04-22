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


text = """[START]
CHUNK_TEST_000:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
CHUNK_TEST_001:abcdefghijklmnopqrstuvwxyz0123456789
CHUNK_TEST_002:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
CHUNK_TEST_003:abcdefghijklmnopqrstuvwxyz0123456789
CHUNK_TEST_004:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
CHUNK_TEST_005:abcdefghijklmnopqrstuvwxyz0123456789
CHUNK_TEST_006:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
CHUNK_TEST_007:abcdefghijklmnopqrstuvwxyz0123456789
[END]"""


@task("5s")
async def moin():
    print("sent")
    await mesh().async_send_data(
        39108,
        text,
    )


start()

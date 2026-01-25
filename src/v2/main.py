from core import start, task

from core.comms.mesh import mesh

def cbl(host, msg):
    print(f"{host}: {msg}")

mesh().start()
print("mesh started:", mesh()._started)
print("espobj:", mesh()._esp)
try:
    print("esp stats:", mesh()._esp.stats())
except Exception as e:
    print("esp.stats error:", e)
print("peers buffer available:", mesh()._peers.available())
print("neighbors count:", mesh()._neighbors.available())

mesh().callback(cbl)
mesh().rx_enable()

@task(None,async_task=False,boot=True)
def hell():
    mesh().hello()
    print("hello sent")


start()
